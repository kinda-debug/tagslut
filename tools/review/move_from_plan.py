#!/usr/bin/env python3
"""
move_from_plan.py

Execute (move-only) file moves from a simple plan CSV.

This is an operational helper similar to quarantine_from_plan.py but generalized:
- Reads a CSV containing at least: action,path
- For rows with action == MOVE (default), moves each file under a destination root
- Preserves the relative path under --source-root when possible (to avoid collisions)
- Optionally updates the dedupe SQLite DB to keep paths/zones consistent
- Always writes a JSONL log describing what would happen / what happened

Safety:
- Default is dry-run (no moves)
- Never overwrites existing destination files
- Verifies post-move existence and size match (cheap) before DB updates
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import hashlib
import re
import unicodedata

from dedupe.exec import execute_move, record_move_receipt, update_legacy_path_with_receipt
from dedupe.storage.schema import init_db
from dedupe.storage.v3 import (
    ensure_move_plan,
)


@dataclass
class Move:
    src: Path
    dest: Path
    row: Dict[str, str]
    db_where_path: Optional[str] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iter_moves(
    plan_csv: Path,
    source_root: Path,
    dest_root: Path,
    action_value: str,
    *,
    sanitize_mode: str,
) -> Iterable[Move]:
    with plan_csv.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("action") or "").strip().upper() != action_value:
                continue
            src_s = (row.get("path") or "").strip()
            if not src_s:
                continue
            src = Path(src_s)
            if not src.exists():
                continue

            dest_s = (row.get("dest_path") or "").strip()
            if dest_s:
                dest = Path(dest_s)
            else:
                try:
                    rel = src.resolve().relative_to(source_root.resolve())
                    dest = dest_root / rel
                except Exception:
                    dest = dest_root / src.name

            if sanitize_mode != "none":
                dest = _sanitize_path(dest, mode=sanitize_mode)

            db_where = (row.get("db_path") or "").strip() or None

            yield Move(src=src, dest=dest, row=row, db_where_path=db_where)


_FAT32_INVALID_CHARS = set('<>:"/\\\\|?*')
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


def _short_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()[:8]


def _sanitize_component_fat32(component: str, *, max_len: int = 240) -> str:
    # Normalize Unicode to NFC to avoid weird decomposed sequences.
    c = unicodedata.normalize("NFC", component)
    # Replace control chars.
    c = _CTRL_CHARS_RE.sub("_", c)
    # Replace invalid FAT32 characters.
    c = "".join("_" if ch in _FAT32_INVALID_CHARS else ch for ch in c)
    # FAT disallows trailing spaces and periods.
    c = c.rstrip(" .")
    if not c:
        c = "_"
    # Avoid reserved names on Windows-ish environments (still a good idea on FAT).
    upper = c.upper()
    if (
        upper in {"CON", "PRN", "AUX", "NUL"}
        or (upper.startswith("COM") and upper[3:].isdigit())
        or (upper.startswith("LPT") and upper[3:].isdigit())
    ):
        c = f"_{c}"
    if len(c) > max_len:
        suffix = "~" + _short_hash(component)
        c = c[: max_len - len(suffix)] + suffix
    return c


def _sanitize_path(path: Path, *, mode: str) -> Path:
    if mode == "fat32":
        parts = list(path.parts)
        # Preserve absolute root.
        start = 1 if path.is_absolute() else 0
        sanitized = parts[:start]
        for p in parts[start:]:
            sanitized.append(_sanitize_component_fat32(p))
        return Path(*sanitized)
    raise ValueError(f"Unknown sanitize mode: {mode}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Move files under a destination root based on a plan CSV"
    )
    ap.add_argument(
        "plan_csv", type=Path, help="Plan CSV with at least columns: action,path"
    )
    ap.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Root used to preserve relative paths",
    )
    ap.add_argument(
        "--dest-root", type=Path, required=True, help="Destination root for moved files"
    )
    ap.add_argument("--action", default="MOVE", help="Plan action value to execute (default: MOVE)")
    ap.add_argument("--db", type=Path, help="Optional SQLite DB to update paths in (files.path)")
    ap.add_argument(
        "--zone",
        default="staging",
        help="Zone to set when updating DB (default: staging)",
    )
    ap.add_argument(
        "--mgmt-status",
        default="moved_from_plan",
        help="mgmt_status to set when updating DB",
    )
    ap.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL log path (default: artifacts/moves_<ts>.jsonl)",
    )
    ap.add_argument(
        "--sanitize",
        choices=["none", "fat32"],
        default="none",
        help=(
            "Sanitize destination path components (default: none). "
            "Use fat32 when writing to FAT32 volumes."
        ),
    )
    ap.add_argument("--execute", action="store_true", help="Actually move files (default: dry-run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    plan_csv = args.plan_csv.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve()
    dest_root = args.dest_root.expanduser().resolve()
    action_value = str(args.action).strip().upper()

    if args.log is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = Path("artifacts") / f"moves_{ts}.jsonl"
    else:
        log_path = args.log.expanduser().resolve()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    dest_root.mkdir(parents=True, exist_ok=True)

    moves = list(
        _iter_moves(
            plan_csv,
            source_root,
            dest_root,
            action_value,
            sanitize_mode=str(args.sanitize),
        )
    )

    conn: Optional[sqlite3.Connection] = None
    move_plan_id: int | None = None
    if args.db:
        db_path = args.db.expanduser().resolve()
        if db_path.is_dir():
            print(f"ERROR: --db points to a directory, not a SQLite file: {db_path}")
            return 2
        if not db_path.exists():
            print(f"ERROR: --db file does not exist: {db_path}")
            return 2
        conn = sqlite3.connect(str(db_path))
        init_db(conn)
        plan_key = f"move_from_plan:{plan_csv}:{action_value}:{args.zone}:{args.mgmt_status}"
        move_plan_id = ensure_move_plan(
            conn,
            plan_key=plan_key,
            plan_type="move_from_plan",
            plan_path=str(plan_csv),
            policy_version="phase3-executor.v1",
            context={
                "action_value": action_value,
                "zone": str(args.zone),
                "mgmt_status": str(args.mgmt_status),
            },
        )

    moved = 0
    skipped_exists = 0
    skipped_missing = 0
    failed = 0
    with log_path.open("w", encoding="utf-8") as log:
        for m in moves:
            evt: Dict[str, Any] = {
                "event": "move_from_plan",
                "timestamp": _now_iso(),
                "action": action_value,
                "execute": bool(args.execute),
                "src": str(m.src),
                "dest": str(m.dest),
                "zone": str(args.zone),
                "mgmt_status": str(args.mgmt_status),
            }
            if "reason" in m.row:
                evt["reason"] = m.row["reason"]
            receipt = execute_move(
                m.src,
                m.dest,
                execute=bool(args.execute),
                collision_policy="skip",
            )
            evt.update(receipt.to_event_fields())

            if receipt.status == "skip_missing":
                skipped_missing += 1
            elif receipt.status == "skip_dest_exists":
                skipped_exists += 1
            elif receipt.status == "moved":
                moved += 1
            elif receipt.status == "error":
                failed += 1

            if conn is not None:
                write_result = record_move_receipt(
                    conn,
                    receipt=receipt,
                    plan_id=move_plan_id,
                    action=action_value,
                    zone=str(args.zone),
                    mgmt_status=str(args.mgmt_status),
                    script_name="tools/review/move_from_plan.py",
                    details={"reason": m.row.get("reason")},
                )
                evt["move_execution_id"] = write_result.move_execution_id
                evt["provenance_event_id"] = write_result.provenance_event_id
                try:
                    if receipt.status == "moved":
                        update_legacy_path_with_receipt(
                            conn,
                            move_execution_id=write_result.move_execution_id,
                            receipt=receipt,
                            zone=str(args.zone),
                            mgmt_status=str(args.mgmt_status),
                            where_path=m.db_where_path,
                        )
                except Exception as exc:
                    failed += 1
                    evt["result"] = "error"
                    evt["error"] = f"legacy_db_update_failed: {type(exc).__name__}: {exc}"

            log.write(json.dumps(evt, ensure_ascii=False) + "\n")

    if conn is not None:
        conn.commit()
        conn.close()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(
        f"{mode}: planned={len(moves)} moved={moved} "
        f"skipped_missing={skipped_missing} "
        f"skipped_exists={skipped_exists} failed={failed}"
    )
    print(f"Plan: {plan_csv}")
    print(f"Dest root: {dest_root}")
    print(f"Log: {log_path}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
