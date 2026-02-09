#!/usr/bin/env python3
"""Backfill v3 move/provenance rows from historical JSONL logs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from dedupe.storage.schema import init_db
from dedupe.storage.v3 import (
    ensure_move_plan,
    insert_move_execution,
    move_asset_path,
    record_provenance_event,
    upsert_asset_file,
)
from dedupe.utils.db import resolve_db_path

MOVE_EVENTS = {"move_from_plan", "quarantine_move", "file_move"}


def _iter_log_files(paths: list[str]) -> Iterator[Path]:
    for raw in paths:
        candidate = Path(raw).expanduser().resolve()
        if candidate.is_file() and candidate.suffix == ".jsonl":
            yield candidate
            continue
        if candidate.is_dir():
            for file_path in sorted(candidate.rglob("*.jsonl")):
                yield file_path


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _event_status(payload: dict) -> str:
    status = payload.get("result")
    if isinstance(status, str) and status:
        return status
    if payload.get("execute"):
        return "unknown"
    return "dry_run"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill v3 provenance and move rows from JSONL artifacts."
    )
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument(
        "--logs",
        nargs="+",
        default=["artifacts"],
        help="JSONL files or directories to replay (default: artifacts)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write backfill rows (default: dry-run report only)",
    )
    parser.add_argument("--limit", type=int, help="Replay at most N events")
    args = parser.parse_args()

    resolution = resolve_db_path(
        args.db,
        purpose="write" if args.execute else "read",
        allow_create=bool(args.execute),
    )
    db_path = resolution.path

    conn = sqlite3.connect(str(db_path))
    try:
        if args.execute:
            init_db(conn)

        replayed = 0
        matched = 0
        for log_file in _iter_log_files(args.logs):
            plan_id: int | None = None
            for payload in _iter_jsonl(log_file):
                if args.limit and replayed >= args.limit:
                    break

                event = payload.get("event")
                if event not in MOVE_EVENTS:
                    continue

                src = payload.get("src") or payload.get("path")
                dest = payload.get("dest_final") or payload.get("dest")
                status = _event_status(payload)
                executed_at = payload.get("timestamp")
                action = payload.get("action")

                replayed += 1

                if not args.execute:
                    continue

                if plan_id is None:
                    plan_id = ensure_move_plan(
                        conn,
                        plan_key=f"log_replay:{log_file}",
                        plan_type=f"log_replay:{event}",
                        plan_path=str(log_file),
                        policy_version="phase1-backfill.v1",
                        context={"source": "jsonl_replay"},
                    )

                asset_id: int | None = None
                if isinstance(src, str) and isinstance(dest, str) and status == "moved":
                    asset_id = move_asset_path(
                        conn,
                        source_path=src,
                        dest_path=dest,
                    )
                    matched += 1
                elif isinstance(src, str):
                    asset_id = upsert_asset_file(conn, path=src)

                move_execution_id = insert_move_execution(
                    conn,
                    plan_id=plan_id,
                    asset_id=asset_id,
                    source_path=src if isinstance(src, str) else None,
                    dest_path=dest if isinstance(dest, str) else None,
                    action=action if isinstance(action, str) else None,
                    status=status,
                    verification=payload.get("verification"),
                    error=payload.get("error"),
                    details=payload,
                    executed_at=executed_at if isinstance(executed_at, str) else None,
                )
                record_provenance_event(
                    conn,
                    event_type="log_replay_move",
                    status=status,
                    asset_id=asset_id,
                    move_plan_id=plan_id,
                    move_execution_id=move_execution_id,
                    source_path=src if isinstance(src, str) else None,
                    dest_path=dest if isinstance(dest, str) else None,
                    details={"log_file": str(log_file), "raw_event": event},
                    event_time=executed_at if isinstance(executed_at, str) else None,
                )

            if args.limit and replayed >= args.limit:
                break

        if args.execute:
            conn.commit()

        mode = "EXECUTE" if args.execute else "DRY-RUN"
        print(f"{mode}: replayed_events={replayed} moved_events={matched}")
        print(f"DB: {db_path}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
