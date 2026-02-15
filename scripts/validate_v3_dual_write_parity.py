#!/usr/bin/env python3
"""Validate parity between legacy and v3 dual-write tables."""

from __future__ import annotations

import argparse
import sqlite3

from tagslut.utils.db import resolve_db_path

REQUIRED_V3_TABLES = (
    "asset_file",
    "track_identity",
    "asset_link",
    "provenance_event",
    "move_plan",
    "move_execution",
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate v3 dual-write parity against legacy tables."
    )
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on parity mismatches (default: report only)",
    )
    args = parser.parse_args()

    resolution = resolve_db_path(args.db, purpose="read")
    db_path = resolution.path

    conn = sqlite3.connect(str(db_path))
    try:
        missing_tables = [t for t in REQUIRED_V3_TABLES if not _table_exists(conn, t)]
        if missing_tables:
            print("ERROR: missing v3 tables: " + ", ".join(missing_tables))
            return 1

        files_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        asset_count = conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0]
        missing_asset_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM files f
            LEFT JOIN asset_file a ON a.path = f.path
            WHERE a.id IS NULL
            """
        ).fetchone()[0]
        moved_files = conn.execute(
            """
            SELECT COUNT(*) FROM files
            WHERE mgmt_status IN ('moved_from_plan', 'quarantined_from_plan')
            """
        ).fetchone()[0]
        moved_exec = conn.execute(
            "SELECT COUNT(*) FROM move_execution WHERE status = 'moved'"
        ).fetchone()[0]

        print("V3 Parity Summary")
        print(f"  DB: {db_path}")
        print(f"  files rows: {files_count}")
        print(f"  asset_file rows: {asset_count}")
        print(f"  files missing asset_file row: {missing_asset_rows}")
        print(f"  moved files (legacy status): {moved_files}")
        print(f"  move_execution rows (status=moved): {moved_exec}")

        issues: list[str] = []
        if missing_asset_rows > 0:
            issues.append(
                f"files->asset_file parity mismatch: {missing_asset_rows} missing rows"
            )
        if moved_files > 0 and moved_exec == 0:
            issues.append(
                "moved files present in legacy table but no moved rows in move_execution"
            )

        if issues:
            print("WARNINGS:")
            for issue in issues:
                print(f"- {issue}")
            if args.strict:
                return 2
        else:
            print("OK: v3 dual-write parity checks passed")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
