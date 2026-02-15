#!/usr/bin/env python3
"""
quarantine_from_plan.py

Execute (move-only) quarantine actions from a plan CSV.

This is intentionally simple + auditable:
- Reads a CSV containing at least: action,path
- For rows with action == MOVE (default), moves the file under a quarantine root
- Optionally updates the tagslut SQLite DB to keep paths consistent
- Always writes a JSONL log describing what would happen / what happened

Designed for operational safety:
- Default is dry-run (no moves)
- Creates destination parent directories
- Preserves relative path under --library-root when possible to avoid collisions
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

from tagslut.exec import execute_move, record_move_receipt, update_legacy_path_with_receipt
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import (
    ensure_move_plan,
)


@dataclass
class Move:
    src: Path
    dest: Path
    row: Dict[str, str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iter_moves(
    plan_csv: Path,
    library_root: Path,
    quarantine_root: Path,
    action_value: str,
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

            try:
                rel = src.resolve().relative_to(library_root.resolve())
                dest = quarantine_root / rel
            except Exception:
                dest = quarantine_root / src.name

            yield Move(src=src, dest=dest, row=row)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Move files to quarantine based on a plan CSV")
    ap.add_argument(
        "plan_csv", type=Path, help="Plan CSV with at least columns: action,path"
    )
    ap.add_argument(
        "--library-root",
        type=Path,
        required=True,
        help="Root used to preserve relative paths",
    )
    ap.add_argument(
        "--quarantine-root",
        type=Path,
        required=True,
        help="Destination root for quarantined files",
    )
    ap.add_argument("--action", default="MOVE", help="Plan action value to execute (default: MOVE)")
    ap.add_argument("--db", type=Path, help="Optional SQLite DB to update paths in (files.path)")
    ap.add_argument(
        "--mgmt-status",
        default="quarantined_from_plan",
        help="mgmt_status to set when updating DB",
    )
    ap.add_argument(
        "--log",
        type=Path,
        default=None,
        help="JSONL log path (default: artifacts/quarantine_moves_<ts>.jsonl)",
    )
    ap.add_argument("--execute", action="store_true", help="Actually move files (default: dry-run)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    plan_csv = args.plan_csv.expanduser().resolve()
    library_root = args.library_root.expanduser().resolve()
    quarantine_root = args.quarantine_root.expanduser().resolve()
    action_value = str(args.action).strip().upper()

    if args.log is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        log_path = Path("artifacts") / f"quarantine_moves_{ts}.jsonl"
    else:
        log_path = args.log.expanduser().resolve()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_root.mkdir(parents=True, exist_ok=True)

    moves = list(_iter_moves(plan_csv, library_root, quarantine_root, action_value))

    conn: Optional[sqlite3.Connection] = None
    move_plan_id: int | None = None
    if args.db:
        db_path = args.db.expanduser().resolve()
        # Guard against common operator error: passing an empty env var -> "." -> directory.
        if db_path.is_dir():
            print(f"ERROR: --db points to a directory, not a SQLite file: {db_path}")
            print("Fix: set DB to an actual .db path (or omit --db to skip DB updates).")
            return 2
        if not db_path.exists():
            print(f"ERROR: --db file does not exist: {db_path}")
            print("Fix: pass the correct DB path (or omit --db to skip DB updates).")
            return 2
        conn = sqlite3.connect(str(db_path))
        init_db(conn)
        plan_key = f"quarantine_from_plan:{plan_csv}:{action_value}:{args.mgmt_status}"
        move_plan_id = ensure_move_plan(
            conn,
            plan_key=plan_key,
            plan_type="quarantine_from_plan",
            plan_path=str(plan_csv),
            policy_version="phase3-executor.v1",
            context={
                "action_value": action_value,
                "zone": "quarantine",
                "mgmt_status": str(args.mgmt_status),
            },
        )

    moved = 0
    skipped_missing = 0
    skipped_exists = 0
    failed = 0
    with log_path.open("w", encoding="utf-8") as log:
        for m in moves:
            evt: Dict[str, Any] = {
                "event": "quarantine_move",
                "timestamp": _now_iso(),
                "action": action_value,
                "execute": bool(args.execute),
                "src": str(m.src),
                "dest": str(m.dest),
            }
            # Bubble through helpful context fields when present
            for k in (
                "match",
                "group",
                "reason",
                "isrc",
                "checksum",
                "streaminfo_md5",
                "fingerprint",
            ):
                if k in m.row:
                    evt[k] = m.row[k]

            receipt = execute_move(
                m.src,
                m.dest,
                execute=bool(args.execute),
                collision_policy="skip",
            )
            evt.update(receipt.to_event_fields())

            if receipt.status == "moved":
                moved += 1
            elif receipt.status == "skip_missing":
                skipped_missing += 1
            elif receipt.status == "skip_dest_exists":
                skipped_exists += 1
            elif receipt.status == "error":
                failed += 1

            if conn is not None:
                write_result = record_move_receipt(
                    conn,
                    receipt=receipt,
                    plan_id=move_plan_id,
                    action=action_value,
                    zone="quarantine",
                    mgmt_status=str(args.mgmt_status),
                    script_name="tools/review/quarantine_from_plan.py",
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
                            zone="quarantine",
                            mgmt_status=str(args.mgmt_status),
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
        f"skipped_missing={skipped_missing} skipped_exists={skipped_exists} failed={failed}"
    )
    print(f"Plan: {plan_csv}")
    print(f"Quarantine root: {quarantine_root}")
    print(f"Log: {log_path}")
    return 0 if failed == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
