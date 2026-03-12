#!/usr/bin/env python3
"""
audio_dupe_audit.py

Audit DB-registered FLACs for "audio dupes with different metadata".

Scope: paths in the `files` table filtered by one or more --root prefixes.

Checks:
1) Integrity gate (expects flac_ok=1 + integrity_state='valid' if present)
2) Exact-audio signature where available: streaminfo_md5 (non-zero only)
3) Chromaprint fingerprint via `fpcalc` (first N seconds, exact fingerprint match)

Outputs (under --out-dir):
- *_fpcalc_groups.csv   : duplicate groups by fingerprint (count>1)
- *_fpcalc_members.csv  : per-file rows for each duplicate group
- *_fpcalc_errors.csv   : fpcalc failures (if any)
- *_summary.json        : counts and file paths of produced artifacts

This script does NOT move files.
DB updates are optional and limited to writing `files.fingerprint` when --execute is supplied.
Fingerprint computation can be limited to specific roots via `--compute-root`.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@dataclass(frozen=True)
class DbFileRow:
    path: str
    size: int | None
    duration: float | None
    sample_rate: int | None
    bit_depth: int | None
    bitrate: int | None
    streaminfo_md5: str | None
    fingerprint: str | None
    flac_ok: int | None
    integrity_state: str | None
    metadata_json: str | None


@dataclass(frozen=True)
class FingerprintResult:
    path: str
    fingerprint: str | None
    duration: float | None
    error: str | None


logger = logging.getLogger("tagslut")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value).strip()


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()


def _where_paths(prefixes: Iterable[Path]) -> tuple[str, list[str]]:
    parts: list[str] = []
    params: list[str] = []
    for prefix in prefixes:
        expanded = str(prefix.expanduser().resolve())
        if not expanded.endswith("/"):
            expanded += "/"
        parts.append("path LIKE ?")
        params.append(expanded + "%")
    if not parts:
        return "1=0", []
    return "(" + " OR ".join(parts) + ")", params


def _matches_root_prefix(path_str: str, prefixes: Iterable[Path]) -> bool:
    for prefix in prefixes:
        expanded = str(prefix.expanduser().resolve())
        if not expanded.endswith("/"):
            expanded += "/"
        if path_str.startswith(expanded):
            return True
    return False


def _load_db_rows(conn: sqlite3.Connection, roots: list[Path]) -> list[DbFileRow]:
    where, params = _where_paths(roots)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""
        SELECT
            path,
            size,
            duration,
            sample_rate,
            bit_depth,
            bitrate,
            streaminfo_md5,
            fingerprint,
            flac_ok,
            integrity_state,
            metadata_json
        FROM files
        WHERE {where}
        ORDER BY path
        """,
        params,
    ).fetchall()
    out: list[DbFileRow] = []
    for r in rows:
        out.append(
            DbFileRow(
                path=r["path"],
                size=r["size"],
                duration=r["duration"],
                sample_rate=r["sample_rate"],
                bit_depth=r["bit_depth"],
                bitrate=r["bitrate"],
                streaminfo_md5=r["streaminfo_md5"],
                fingerprint=r["fingerprint"],
                flac_ok=r["flac_ok"],
                integrity_state=r["integrity_state"],
                metadata_json=r["metadata_json"],
            )
        )
    return out


def _fpcalc_worker(item: tuple[str, int, int]) -> FingerprintResult:
    path_str, length_s, timeout_s = item
    try:
        res = subprocess.run(
            ["fpcalc", "-json", "-length", str(length_s), path_str],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return FingerprintResult(path=path_str, fingerprint=None, duration=None, error="fpcalc binary missing")
    except subprocess.TimeoutExpired:
        return FingerprintResult(path=path_str, fingerprint=None, duration=None, error=f"fpcalc timeout>{timeout_s}s")
    except Exception as e:
        return FingerprintResult(path=path_str, fingerprint=None, duration=None, error=f"{type(e).__name__}: {e}")

    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        return FingerprintResult(
            path=path_str,
            fingerprint=None,
            duration=None,
            error=f"fpcalc rc={res.returncode}: {stderr[:400]}",
        )

    try:
        payload = json.loads(res.stdout or "{}")
    except Exception as e:
        return FingerprintResult(path=path_str, fingerprint=None, duration=None, error=f"fpcalc json error: {e}")

    fp = str(payload.get("fingerprint", "") or "").strip()
    duration_val: float | None = None
    try:
        if payload.get("duration") is not None:
            duration_val = float(payload.get("duration"))
    except Exception:
        duration_val = None

    if not fp:
        return FingerprintResult(path=path_str, fingerprint=None, duration=duration_val, error="fpcalc empty fingerprint")
    return FingerprintResult(path=path_str, fingerprint=fp, duration=duration_val, error=None)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Audit audio duplicates across DB-registered files under roots")
    ap.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite DB path (default: $TAGSLUT_DB)",
    )
    ap.add_argument(
        "--root",
        type=Path,
        action="append",
        required=True,
        help="Root prefix filter (repeatable)",
    )
    ap.add_argument(
        "--compute-root",
        type=Path,
        action="append",
        default=[],
        help="Root prefix eligible for missing fingerprint computation (default: all --root values)",
    )
    ap.add_argument("--workers", type=int, default=None, help="Parallel workers (default: CPU-1)")
    ap.add_argument("--fp-length", type=int, default=120, help="fpcalc fingerprint length in seconds (default: 120)")
    ap.add_argument("--fp-timeout", type=int, default=180, help="fpcalc timeout per file in seconds (default: 180)")
    ap.add_argument("--recompute", action="store_true", help="Recompute fingerprints even if present in DB")
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory")
    ap.add_argument("--limit", type=int, help="Limit number of files (for testing)")
    ap.add_argument("--execute", action="store_true", help="Write fingerprints back to DB (default: dry-run)")
    ap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (implies --progress)",
    )
    ap.add_argument("--progress", action="store_true", help="Emit periodic progress via tagslut logger")
    ap.add_argument("--progress-interval", type=int, default=250, help="Progress interval (items)")
    return ap.parse_args()


def _path_root_label(path_str: str, roots: list[Path]) -> str:
    # Return the first matching root label; else empty.
    for r in roots:
        prefix = str(r.expanduser().resolve())
        if not prefix.endswith("/"):
            prefix += "/"
        if path_str.startswith(prefix):
            # Use the last path component of root for readability.
            return r.name or prefix.rstrip("/").split("/")[-1]
    return ""


def _safe_load_meta(metadata_json: Optional[str]) -> dict[str, Any]:
    if not metadata_json:
        return {}
    try:
        obj = json.loads(metadata_json)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parse_args()
    if args.verbose or args.progress:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
        )
        logger.setLevel(logging.INFO)

    db_path = (args.db or Path(os.environ.get("TAGSLUT_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $TAGSLUT_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    roots = [p.expanduser().resolve() for p in args.root]
    compute_roots = [p.expanduser().resolve() for p in args.compute_root] if args.compute_root else list(roots)
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = _now_stamp()
    out_groups = out_dir / f"audio_dupe_audit_fpcalc_groups_{stamp}.csv"
    out_members = out_dir / f"audio_dupe_audit_fpcalc_members_{stamp}.csv"
    out_errors = out_dir / f"audio_dupe_audit_fpcalc_errors_{stamp}.csv"
    out_summary = out_dir / f"audio_dupe_audit_summary_{stamp}.json"

    conn = sqlite3.connect(str(db_path))
    try:
        db_rows = _load_db_rows(conn, roots)
    finally:
        conn.close()

    if args.limit and args.limit > 0:
        db_rows = db_rows[: args.limit]

    if not db_rows:
        print("No DB rows matched roots.")
        return 0

    logger.info("Scoped DB rows: %d", len(db_rows))

    # Determine fpcalc work list
    pending_paths: list[str] = []
    existing_fp = 0
    skipped_scope = 0
    for row in db_rows:
        if not args.recompute and row.fingerprint:
            existing_fp += 1
            continue
        if not _matches_root_prefix(row.path, compute_roots):
            skipped_scope += 1
            continue
        pending_paths.append(row.path)

    logger.info(
        "Fingerprints in DB: %d | Eligible missing: %d | To compute: %d",
        existing_fp,
        skipped_scope + len(pending_paths),
        len(pending_paths),
    )

    # Compute fingerprints in parallel
    fp_by_path: dict[str, FingerprintResult] = {}
    if pending_paths:
        try:
            from tagslut.utils.parallel import process_map
        except Exception as e:
            raise SystemExit(f"ERROR: could not import process_map: {e}")

        work_items = [(p, int(args.fp_length), int(args.fp_timeout)) for p in pending_paths]
        results = process_map(
            _fpcalc_worker,
            work_items,
            max_workers=args.workers,
            progress=bool(args.progress or args.verbose),
            progress_interval=int(args.progress_interval),
        )
        for r in results:
            fp_by_path[r.path] = r

    # Optional DB update
    updated = 0
    missing_db_updates = 0
    if args.execute and fp_by_path:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("BEGIN")
            updates: list[tuple[str, str]] = []
            for r in fp_by_path.values():
                if r.fingerprint:
                    updates.append((r.fingerprint, r.path))
            conn.executemany("UPDATE files SET fingerprint=? WHERE path=?", updates)
            updated = conn.total_changes
            # Some sqlite builds report total_changes including BEGIN; ensure we compute missing rows explicitly.
            if updates:
                cur = conn.execute(
                    "SELECT COUNT(*) FROM files WHERE path IN ({})".format(",".join("?" for _ in updates)),
                    tuple(p for _, p in updates),
                )
                matched = int(cur.fetchone()[0])
                missing_db_updates = max(0, len(updates) - matched)
            conn.commit()
        finally:
            conn.close()

    # Build final fingerprint map for grouping (DB values + computed)
    final_fp_by_path: dict[str, str] = {}
    failures: list[FingerprintResult] = []
    computed_ok = 0
    computed_fail = 0
    for row in db_rows:
        fp_val = (row.fingerprint or "").strip()
        if fp_val and not args.recompute:
            final_fp_by_path[row.path] = fp_val
            continue
        res = fp_by_path.get(row.path)
        if res and res.fingerprint:
            final_fp_by_path[row.path] = res.fingerprint
            computed_ok += 1
        else:
            computed_fail += 1
            if res and res.error:
                failures.append(res)

    # Duplicate groups by fingerprint (exact match)
    members_by_fp: dict[str, list[DbFileRow]] = {}
    row_by_path = {r.path: r for r in db_rows}
    for path_str, fp_val in final_fp_by_path.items():
        members_by_fp.setdefault(fp_val, []).append(row_by_path[path_str])

    dupe_groups = [(fp_val, members) for fp_val, members in members_by_fp.items() if len(members) > 1]
    dupe_groups.sort(key=lambda t: (-len(t[1]), _sha1_text(t[0])))

    # Write reports
    group_fieldnames = [
        "group_id",
        "fp_sha1",
        "count",
        "roots",
        "metadata_diff",
        "unique_artist",
        "unique_title",
        "unique_album",
        "unique_isrc",
        "duration_spread_s",
        "sample_rates",
        "bit_depths",
        "bitrates",
        "paths",
    ]
    member_fieldnames = [
        "group_id",
        "fp_sha1",
        "root",
        "path",
        "size",
        "duration",
        "sample_rate",
        "bit_depth",
        "bitrate",
        "streaminfo_md5",
        "artist",
        "title",
        "album",
        "isrc",
        "label",
        "date",
        "beatport_track_id",
    ]

    with out_groups.open("w", newline="", encoding="utf-8") as f_groups, out_members.open(
        "w", newline="", encoding="utf-8"
    ) as f_members:
        w_groups = csv.DictWriter(f_groups, fieldnames=group_fieldnames)
        w_members = csv.DictWriter(f_members, fieldnames=member_fieldnames)
        w_groups.writeheader()
        w_members.writeheader()

        for idx, (fp_val, members) in enumerate(dupe_groups, start=1):
            fp_sha1 = _sha1_text(fp_val)
            roots_set: set[str] = set()

            artists_norm: set[str] = set()
            titles_norm: set[str] = set()
            albums_norm: set[str] = set()
            isrcs_norm: set[str] = set()

            durations: list[float] = []
            sample_rates: set[int] = set()
            bit_depths: set[int] = set()
            bitrates: set[int] = set()

            paths_sorted = sorted([m.path for m in members])
            for m in members:
                roots_set.add(_path_root_label(m.path, roots))

                if m.duration is not None:
                    durations.append(float(m.duration))
                if m.sample_rate is not None:
                    sample_rates.add(int(m.sample_rate))
                if m.bit_depth is not None:
                    bit_depths.add(int(m.bit_depth))
                if m.bitrate is not None:
                    bitrates.add(int(m.bitrate))

                meta = _safe_load_meta(m.metadata_json)
                artist = _norm_text(meta.get("artist") or meta.get("albumartist"))
                title = _norm_text(meta.get("title"))
                album = _norm_text(meta.get("album"))
                isrc = _norm_text(meta.get("isrc"))

                if artist:
                    artists_norm.add(artist.lower())
                if title:
                    titles_norm.add(title.lower())
                if album:
                    albums_norm.add(album.lower())
                if isrc:
                    isrcs_norm.add(isrc.lower())

                w_members.writerow(
                    {
                        "group_id": str(idx),
                        "fp_sha1": fp_sha1,
                        "root": _path_root_label(m.path, roots),
                        "path": m.path,
                        "size": "" if m.size is None else str(m.size),
                        "duration": "" if m.duration is None else f"{float(m.duration):.3f}",
                        "sample_rate": "" if m.sample_rate is None else str(m.sample_rate),
                        "bit_depth": "" if m.bit_depth is None else str(m.bit_depth),
                        "bitrate": "" if m.bitrate is None else str(m.bitrate),
                        "streaminfo_md5": m.streaminfo_md5 or "",
                        "artist": artist,
                        "title": title,
                        "album": album,
                        "isrc": isrc,
                        "label": _norm_text(meta.get("label")),
                        "date": _norm_text(meta.get("date")),
                        "beatport_track_id": _norm_text(meta.get("beatport_track_id")),
                    }
                )

            duration_spread: float | None = None
            if durations:
                duration_spread = max(durations) - min(durations)

            metadata_diff = 1 if (len(artists_norm) > 1 or len(titles_norm) > 1 or len(albums_norm) > 1 or len(isrcs_norm) > 1) else 0

            w_groups.writerow(
                {
                    "group_id": str(idx),
                    "fp_sha1": fp_sha1,
                    "count": str(len(members)),
                    "roots": " | ".join(sorted(r for r in roots_set if r)),
                    "metadata_diff": str(metadata_diff),
                    "unique_artist": str(len(artists_norm)),
                    "unique_title": str(len(titles_norm)),
                    "unique_album": str(len(albums_norm)),
                    "unique_isrc": str(len(isrcs_norm)),
                    "duration_spread_s": "" if duration_spread is None else f"{duration_spread:.3f}",
                    "sample_rates": " | ".join(str(x) for x in sorted(sample_rates)),
                    "bit_depths": " | ".join(str(x) for x in sorted(bit_depths)),
                    "bitrates": " | ".join(str(x) for x in sorted(bitrates)),
                    "paths": " | ".join(paths_sorted),
                }
            )

    if failures:
        with out_errors.open("w", newline="", encoding="utf-8") as f_err:
            w_err = csv.DictWriter(f_err, fieldnames=["path", "error"])
            w_err.writeheader()
            for r in failures:
                w_err.writerow({"path": r.path, "error": r.error or "unknown"})
    else:
        # Still create the file for predictable tooling
        out_errors.write_text("path,error\n", encoding="utf-8")

    # Streaminfo MD5 dupe groups (non-zero only; stored as NULL when unknown)
    conn = sqlite3.connect(str(db_path))
    try:
        where, params = _where_paths(roots)
        cur = conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT streaminfo_md5, COUNT(*) c
                FROM files
                WHERE streaminfo_md5 IS NOT NULL AND streaminfo_md5 != '' AND {where}
                GROUP BY streaminfo_md5
                HAVING c > 1
            )
            """,
            params,
        )
        streaminfo_dupe_groups = int(cur.fetchone()[0])
    finally:
        conn.close()

    summary = {
        "db": str(db_path),
        "roots": [str(r) for r in roots],
        "compute_roots": [str(r) for r in compute_roots],
        "total_files": len(db_rows),
        "integrity_valid": sum(1 for r in db_rows if (r.integrity_state or "").strip() == "valid"),
        "flac_ok": sum(1 for r in db_rows if r.flac_ok == 1),
        "streaminfo_md5_present": sum(1 for r in db_rows if (r.streaminfo_md5 or "").strip()),
        "streaminfo_md5_dupe_groups_nonzero": streaminfo_dupe_groups,
        "fingerprint_existing_in_db": existing_fp,
        "fingerprint_missing_outside_compute_scope": skipped_scope,
        "fingerprint_computed_ok": computed_ok,
        "fingerprint_computed_fail": computed_fail,
        "fingerprint_dupe_groups": len(dupe_groups),
        "fingerprint_dupe_files": sum(len(members) for _, members in dupe_groups),
        "db_updated": bool(args.execute),
        "db_rows_updated": updated,
        "db_updates_missing_rows": missing_db_updates,
        "artifacts": {
            "groups_csv": str(out_groups),
            "members_csv": str(out_members),
            "errors_csv": str(out_errors),
        },
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Files scoped: {len(db_rows)}")
    print(
        f"fpcalc computed: ok={computed_ok} fail={computed_fail} "
        f"(existing_in_db={existing_fp} missing_outside_scope={skipped_scope})"
    )
    print(f"Fingerprint dupe groups: {len(dupe_groups)} (files_in_groups={sum(len(m) for _, m in dupe_groups)})")
    print(f"STREAMINFO_MD5 dupe groups (non-zero): {streaminfo_dupe_groups}")
    if args.execute:
        print(f"DB updated fingerprint rows: {updated} (missing_rows={missing_db_updates})")
    print(f"Wrote: {out_groups}")
    print(f"Wrote: {out_members}")
    print(f"Wrote: {out_errors}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
