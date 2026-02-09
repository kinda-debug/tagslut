#!/usr/bin/env python3
"""
check_integrity_update_db.py

Run `flac -t` integrity checks for files already registered in the dedupe DB,
and write results back to the DB.

This is intentionally *DB-only* (no file moves) and does NOT overwrite hashes.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class IntegrityResult:
    path: str
    state: str  # valid | recoverable | corrupt
    flac_ok: int  # 1/0
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _classify_flac(path: str) -> IntegrityResult:
    p = Path(path)
    if not p.exists():
        return IntegrityResult(path=path, state="corrupt", flac_ok=0, error="File not found")
    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(p)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return IntegrityResult(path=path, state="valid", flac_ok=1)
        stderr = (res.stderr or "").strip()
        if "MD5" in stderr.upper():
            return IntegrityResult(path=path, state="recoverable", flac_ok=0, error=stderr[:400])
        return IntegrityResult(path=path, state="corrupt", flac_ok=0, error=stderr[:400] or "Unknown FLAC error")
    except FileNotFoundError:
        return IntegrityResult(path=path, state="corrupt", flac_ok=0, error="flac binary missing")
    except Exception as e:
        return IntegrityResult(path=path, state="corrupt", flac_ok=0, error=f"{type(e).__name__}: {e}")


def _iter_db_paths(conn: sqlite3.Connection, roots: list[Path], recheck: bool) -> Iterable[str]:
    clauses: list[str] = []
    params: list[str] = []
    for root in roots:
        prefix = str(root.expanduser().resolve())
        if not prefix.endswith("/"):
            prefix += "/"
        clauses.append("path LIKE ?")
        params.append(prefix + "%")
    where = "(" + " OR ".join(clauses) + ")" if clauses else "1=0"
    extra = "" if recheck else " AND integrity_checked_at IS NULL"
    q = f"SELECT path FROM files WHERE {where}{extra} ORDER BY path"
    for row in conn.execute(q, tuple(params)):
        yield row[0]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run flac -t for DB-registered files and write results back")
    ap.add_argument("roots", nargs="+", type=Path, help="Root directories to process (prefix match in DB)")
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $DEDUPE_DB)")
    ap.add_argument("--workers", type=int, default=None, help="Parallel workers (default: CPU-1)")
    ap.add_argument("--progress", action="store_true", help="Log periodic progress")
    ap.add_argument("--progress-interval", type=int, default=250, help="Progress interval (files)")
    ap.add_argument("--recheck", action="store_true", help="Re-check even if integrity_checked_at already set")
    ap.add_argument("--limit", type=int, help="Limit number of files (for testing)")
    ap.add_argument("--log", type=Path, default=None, help="JSONL log path (default: artifacts/integrity_<ts>.jsonl)")
    ap.add_argument("--execute", action="store_true", help="Write updates to DB (default: dry-run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    db_path = (args.db or Path(os.environ.get("DEDUPE_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $DEDUPE_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    roots = [r.expanduser().resolve() for r in args.roots]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = (args.log or Path("artifacts") / f"integrity_{ts}.jsonl").expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        paths = list(_iter_db_paths(conn, roots, recheck=bool(args.recheck)))
    finally:
        conn.close()

    if args.limit and args.limit > 0:
        paths = paths[: args.limit]

    if not paths:
        print("No files matched (or all already checked).")
        return 0

    # Parallel check
    try:
        from dedupe.utils.parallel import process_map
    except Exception as e:
        raise SystemExit(f"ERROR: could not import process_map: {e}")

    interrupted = False
    results = process_map(
        _classify_flac,
        paths,
        max_workers=args.workers,
        progress=bool(args.progress),
        progress_interval=int(args.progress_interval),
        return_interrupt_status=True,
    )
    # process_map returns ProcessMapResult when return_interrupt_status=True
    try:
        raw = results  # type: ignore[assignment]
        results_list = raw.results  # type: ignore[attr-defined]
        interrupted = bool(raw.interrupted)  # type: ignore[attr-defined]
    except Exception:
        results_list = results  # type: ignore[assignment]

    now_iso = _now_iso()
    counts: dict[str, int] = {"valid": 0, "recoverable": 0, "corrupt": 0}
    missing_db = 0

    # Write log and optional DB updates
    conn = sqlite3.connect(str(db_path))
    try:
        if args.execute:
            conn.execute("BEGIN")
        with log_path.open("w", encoding="utf-8") as log:
            for r in results_list:
                counts[r.state] = counts.get(r.state, 0) + 1
                log.write(
                    json.dumps(
                        {
                            "event": "flac_test",
                            "timestamp": now_iso,
                            "path": r.path,
                            "state": r.state,
                            "flac_ok": int(r.flac_ok),
                            "error": r.error,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if not args.execute:
                    continue
                cur = conn.execute(
                    "UPDATE files SET flac_ok=?, integrity_state=?, integrity_checked_at=? WHERE path=?",
                    (int(r.flac_ok), r.state, now_iso, r.path),
                )
                if cur.rowcount == 0:
                    missing_db += 1
        if args.execute:
            conn.commit()
    finally:
        conn.close()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    total = len(results_list)
    print(f"{mode}: checked={total} valid={counts.get('valid',0)} recoverable={counts.get('recoverable',0)} corrupt={counts.get('corrupt',0)}")
    if missing_db:
        print(f"WARNING: {missing_db} path(s) were not found in DB at update time")
    if interrupted:
        print("WARNING: interrupted; partial results written")
    print(f"DB: {db_path}")
    print(f"Log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

