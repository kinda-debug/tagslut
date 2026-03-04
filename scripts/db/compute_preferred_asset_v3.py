#!/usr/bin/env python3
"""Plan/apply deterministic preferred-asset selection for v3 identities."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.db.v3.preferred_asset import (  # noqa: E402
    PreferredChoice,
    choose_preferred_asset_for_identity,
    upsert_preferred_assets,
)
from tagslut.db.v3.schema import create_schema_v3  # noqa: E402

PLAN_COLUMNS = [
    "identity_id",
    "identity_key",
    "chosen_asset_id",
    "chosen_path",
    "score",
    "reason_json",
]


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _connect_rw(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    conn = sqlite3.connect(str(resolved))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _active_identity_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "track_identity", "merged_into_id"):
        return "merged_into_id IS NULL"
    return "1=1"


def _load_active_identities(conn: sqlite3.Connection, limit: int | None) -> list[sqlite3.Row]:
    where_active = _active_identity_where(conn)
    sql = (
        "SELECT id, identity_key FROM track_identity "
        f"WHERE {where_active} ORDER BY id ASC"
    )
    params: tuple[object, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    return conn.execute(sql, params).fetchall()


def _compute_choices_for_rows(
    conn: sqlite3.Connection, identity_rows: list[sqlite3.Row]
) -> tuple[list[PreferredChoice], int]:
    choices: list[PreferredChoice] = []
    skipped_no_assets = 0
    for row in identity_rows:
        identity_id = int(row["id"])
        try:
            choices.append(choose_preferred_asset_for_identity(conn, identity_id))
        except LookupError:
            skipped_no_assets += 1
    return choices, skipped_no_assets


def _write_plan_csv(out_path: Path, choices: list[PreferredChoice]) -> Path:
    resolved = out_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_COLUMNS)
        writer.writeheader()
        for choice in choices:
            writer.writerow(
                {
                    "identity_id": choice.identity_id,
                    "identity_key": choice.identity_key,
                    "chosen_asset_id": choice.asset_id,
                    "chosen_path": choice.chosen_path,
                    "score": choice.score,
                    "reason_json": choice.reason_json,
                }
            )
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute preferred assets for v3 identities")
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument("--limit", type=int, help="Optional identity limit")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write preferred_asset table (default is plan-only)",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="Version marker written to preferred_asset.version (default: 1)",
    )
    parser.add_argument("--out", type=Path, help="Optional plan CSV output path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2
    if int(args.version) <= 0:
        print("--version must be > 0")
        return 2

    db_path = args.db.expanduser().resolve()
    execute_mode = bool(args.execute)
    try:
        conn = _connect_rw(db_path) if execute_mode else _connect_ro(db_path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        if execute_mode:
            create_schema_v3(conn)

        identity_rows = _load_active_identities(conn, args.limit)
        active_identities = len(identity_rows)
        choices, skipped_no_assets = _compute_choices_for_rows(conn, identity_rows)
        identities_with_assets = len(choices)

        written_counts = {
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "written": 0,
        }
        if execute_mode:
            written_counts = upsert_preferred_assets(
                conn,
                choices,
                version=int(args.version),
            )
            conn.commit()
    finally:
        conn.close()

    out_path: Path | None = None
    if args.out is not None:
        out_path = _write_plan_csv(args.out, choices)

    print(f"v3 db: {db_path}")
    print(f"mode: {'execute' if execute_mode else 'plan'}")
    print(f"active_identities: {active_identities}")
    print(f"identities_with_assets: {identities_with_assets}")
    print(f"choices_planned: {len(choices)}")
    print(f"skipped_no_assets: {skipped_no_assets}")
    if execute_mode:
        print(f"version: {int(args.version)}")
        print(f"rows_inserted: {written_counts['inserted']}")
        print(f"rows_updated: {written_counts['updated']}")
        print(f"rows_unchanged: {written_counts['unchanged']}")
        print(f"rows_written: {written_counts['written']}")
    if out_path is not None:
        print(f"plan_csv: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
