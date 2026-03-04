#!/usr/bin/env python3
"""Check post-promote invariant: preferred-under-root must be selected when available."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_MINUTES = 240
DEFAULT_LIMIT = 200


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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _resolve_since_ts(*, since: str | None, minutes: int) -> str:
    if since:
        return since.strip()
    dt = datetime.now(UTC) - timedelta(minutes=int(minutes))
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _count_promoted_rows(conn: sqlite3.Connection, *, root_prefix: str, since_ts: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM provenance_event pe
        WHERE pe.event_type = 'promotion_select'
          AND pe.status = 'moved'
          AND pe.identity_id IS NOT NULL
          AND pe.source_path LIKE ? || '%'
          AND datetime(pe.event_time) >= datetime(?)
        """,
        (root_prefix, since_ts),
    ).fetchone()
    return int(row["n"]) if row else 0


def _count_preferred_under_root_identities(conn: sqlite3.Connection, *, root_prefix: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT pa.identity_id) AS n
        FROM preferred_asset pa
        JOIN asset_file af ON af.id = pa.asset_id
        WHERE af.path LIKE ? || '%'
        """,
        (root_prefix,),
    ).fetchone()
    return int(row["n"]) if row else 0


def _load_violations(
    conn: sqlite3.Connection,
    *,
    root_prefix: str,
    since_ts: str,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        WITH promoted AS (
            SELECT
                pe.identity_id,
                pe.asset_id AS chosen_asset_id,
                pe.source_path,
                pe.event_time
            FROM provenance_event pe
            WHERE pe.event_type = 'promotion_select'
              AND pe.status = 'moved'
              AND pe.identity_id IS NOT NULL
              AND pe.source_path LIKE ? || '%'
              AND datetime(pe.event_time) >= datetime(?)
        ),
        preferred_under_root AS (
            SELECT
                pa.identity_id,
                pa.asset_id AS preferred_asset_id
            FROM preferred_asset pa
            JOIN asset_file af ON af.id = pa.asset_id
            WHERE af.path LIKE ? || '%'
        )
        SELECT
            p.identity_id,
            p.chosen_asset_id,
            pur.preferred_asset_id,
            p.source_path,
            p.event_time
        FROM promoted p
        JOIN preferred_under_root pur ON pur.identity_id = p.identity_id
        WHERE p.chosen_asset_id != pur.preferred_asset_id
        ORDER BY datetime(p.event_time) DESC, p.identity_id ASC
        LIMIT ?
        """,
        (root_prefix, since_ts, root_prefix, int(limit)),
    ).fetchall()


def _count_violations(conn: sqlite3.Connection, *, root_prefix: str, since_ts: str) -> int:
    row = conn.execute(
        """
        WITH promoted AS (
            SELECT
                pe.identity_id,
                pe.asset_id AS chosen_asset_id
            FROM provenance_event pe
            WHERE pe.event_type = 'promotion_select'
              AND pe.status = 'moved'
              AND pe.identity_id IS NOT NULL
              AND pe.source_path LIKE ? || '%'
              AND datetime(pe.event_time) >= datetime(?)
        ),
        preferred_under_root AS (
            SELECT
                pa.identity_id,
                pa.asset_id AS preferred_asset_id
            FROM preferred_asset pa
            JOIN asset_file af ON af.id = pa.asset_id
            WHERE af.path LIKE ? || '%'
        )
        SELECT COUNT(*) AS n
        FROM promoted p
        JOIN preferred_under_root pur ON pur.identity_id = p.identity_id
        WHERE p.chosen_asset_id != pur.preferred_asset_id
        """,
        (root_prefix, since_ts, root_prefix),
    ).fetchone()
    return int(row["n"]) if row else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check promotion preferred-asset invariant")
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument("--root", required=True, help="Promoted root prefix")
    parser.add_argument("--since", help="ISO timestamp lower bound for promote events")
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_MINUTES,
        help=f"Window in minutes when --since is omitted (default: {DEFAULT_MINUTES})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Max violation rows to print (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--strict",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Exit non-zero when violations exist (default: true)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.minutes <= 0:
        print("--minutes must be > 0")
        return 2
    if args.limit <= 0:
        print("--limit must be > 0")
        return 2
    root_prefix = str(args.root).strip()
    if not root_prefix:
        print("--root must not be empty")
        return 2
    since_ts = _resolve_since_ts(since=args.since, minutes=int(args.minutes))

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        if not _table_exists(conn, "provenance_event"):
            print("missing required table: provenance_event")
            return 2
        if not _table_exists(conn, "preferred_asset"):
            print("missing required table: preferred_asset")
            return 2
        if not _table_exists(conn, "asset_file"):
            print("missing required table: asset_file")
            return 2

        promoted_rows = _count_promoted_rows(conn, root_prefix=root_prefix, since_ts=since_ts)
        preferred_under_root = _count_preferred_under_root_identities(conn, root_prefix=root_prefix)
        violation_count = _count_violations(conn, root_prefix=root_prefix, since_ts=since_ts)
        violations = _load_violations(
            conn,
            root_prefix=root_prefix,
            since_ts=since_ts,
            limit=int(args.limit),
        )
    except sqlite3.DatabaseError as exc:
        print(f"failed to query v3 db: {exc}")
        return 1
    finally:
        conn.close()

    print(f"root_prefix: {root_prefix}")
    print(f"since_ts: {since_ts}")
    print(f"promoted_rows: {promoted_rows}")
    print(f"preferred_under_root_identities: {preferred_under_root}")
    print(f"violation_count: {violation_count}")

    if violation_count > 0:
        print(f"violations_sample(limit={int(args.limit)}):")
        for row in violations:
            print(
                "  "
                f"identity_id={int(row['identity_id'])} "
                f"chosen_asset_id={int(row['chosen_asset_id'])} "
                f"preferred_asset_id={int(row['preferred_asset_id'])} "
                f"source_path={row['source_path']} "
                f"event_time={row['event_time']}"
            )
        if bool(args.strict):
            return 1
        return 0

    print("OK: promotion preferred-asset invariant holds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
