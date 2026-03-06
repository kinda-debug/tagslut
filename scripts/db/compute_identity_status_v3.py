#!/usr/bin/env python3
"""Compute lifecycle status rows for standalone v3 identities."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.identity_status import (  # noqa: E402
    compute_identity_statuses,
    summary_counts,
    upsert_identity_statuses,
)
from tagslut.storage.v3.schema import create_schema_v3  # noqa: E402

DEFAULT_LIMIT = 200
CSV_COLUMNS = [
    "identity_id",
    "identity_key",
    "isrc",
    "beatport_id",
    "canonical_artist",
    "canonical_title",
    "computed_status",
    "asset_count",
    "merged_into_id",
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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _table_column_expr(
    conn: sqlite3.Connection,
    *,
    schema_table: str,
    table_alias: str,
    column: str,
    alias: str,
) -> str:
    if _column_exists(conn, schema_table, column):
        return f"{table_alias}.{column} AS {alias}"
    return f"NULL AS {alias}"


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "al.active = 1"
    return "1=1"


def _merged_select_expr(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "track_identity", "merged_into_id"):
        return "ti.merged_into_id AS merged_into_id"
    return "NULL AS merged_into_id"


def _load_effective_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    status_rows = compute_identity_statuses(conn)
    computed_status_by_id = {row.identity_id: row.computed_status for row in status_rows}
    archived_ids: set[int] = set()
    if _table_exists(conn, "identity_status"):
        archived = conn.execute(
            """
            SELECT identity_id
            FROM identity_status
            WHERE status = 'archived'
            """
        ).fetchall()
        archived_ids = {int(row["identity_id"]) for row in archived}

    active_link_where = _active_link_where(conn)
    merged_select = _merged_select_expr(conn)
    identity_key_expr = _table_column_expr(
        conn,
        schema_table="track_identity",
        table_alias="ti",
        column="identity_key",
        alias="identity_key",
    )
    isrc_expr = _table_column_expr(
        conn,
        schema_table="track_identity",
        table_alias="ti",
        column="isrc",
        alias="isrc",
    )
    beatport_id_expr = _table_column_expr(
        conn,
        schema_table="track_identity",
        table_alias="ti",
        column="beatport_id",
        alias="beatport_id",
    )
    canonical_artist_expr = _table_column_expr(
        conn,
        schema_table="track_identity",
        table_alias="ti",
        column="canonical_artist",
        alias="canonical_artist",
    )
    canonical_title_expr = _table_column_expr(
        conn,
        schema_table="track_identity",
        table_alias="ti",
        column="canonical_title",
        alias="canonical_title",
    )
    rows = conn.execute(
        f"""
        SELECT
            ti.id AS identity_id,
            {identity_key_expr},
            {isrc_expr},
            {beatport_id_expr},
            {canonical_artist_expr},
            {canonical_title_expr},
            {merged_select},
            COUNT(DISTINCT CASE WHEN {active_link_where} THEN al.asset_id END) AS asset_count
        FROM track_identity ti
        LEFT JOIN asset_link al ON al.identity_id = ti.id
        GROUP BY ti.id
        ORDER BY ti.id ASC
        """
    ).fetchall()

    out: list[dict[str, object]] = []
    for row in rows:
        identity_id = int(row["identity_id"])
        merged_into_raw = row["merged_into_id"]
        merged_into_id = int(merged_into_raw) if merged_into_raw is not None else None
        asset_count = int(row["asset_count"] or 0)
        if merged_into_id is not None:
            effective_status = "merged"
        elif identity_id in archived_ids:
            effective_status = "archived"
        else:
            effective_status = computed_status_by_id.get(
                identity_id,
                "active" if asset_count > 0 else "orphan",
            )
        out.append(
            {
                "identity_id": identity_id,
                "identity_key": str(row["identity_key"] or ""),
                "isrc": str(row["isrc"] or ""),
                "beatport_id": str(row["beatport_id"] or ""),
                "canonical_artist": str(row["canonical_artist"] or ""),
                "canonical_title": str(row["canonical_title"] or ""),
                "computed_status": effective_status,
                "asset_count": asset_count,
                "merged_into_id": merged_into_id,
            }
        )
    return out


def _write_csv(out_path: Path, rows: list[dict[str, object]], limit: int | None) -> Path:
    resolved = out_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    rows_to_write = rows if limit is None else rows[: int(limit)]
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows_to_write:
            writer.writerow(
                {
                    "identity_id": row["identity_id"],
                    "identity_key": row["identity_key"],
                    "isrc": row["isrc"],
                    "beatport_id": row["beatport_id"],
                    "canonical_artist": row["canonical_artist"],
                    "canonical_title": row["canonical_title"],
                    "computed_status": row["computed_status"],
                    "asset_count": row["asset_count"],
                    "merged_into_id": row["merged_into_id"] or "",
                }
            )
    return resolved


def _timestamp_expr_for_archiving(conn: sqlite3.Connection) -> tuple[str | None, str]:
    candidates: list[tuple[str, str]] = []
    if _column_exists(conn, "track_identity", "updated_at"):
        candidates.append(("NULLIF(TRIM(ti.updated_at), '')", "updated_at"))
    if _column_exists(conn, "track_identity", "last_seen_at"):
        candidates.append(("NULLIF(TRIM(ti.last_seen_at), '')", "last_seen_at"))
    if _column_exists(conn, "track_identity", "created_at"):
        candidates.append(("NULLIF(TRIM(ti.created_at), '')", "created_at"))
    if not candidates:
        return None, "none"
    if len(candidates) == 1:
        return candidates[0]
    expr = "COALESCE(" + ", ".join(item[0] for item in candidates) + ")"
    names = ",".join(item[1] for item in candidates)
    return expr, names


def _archive_candidate_ids(
    conn: sqlite3.Connection,
    *,
    threshold_days: int,
    no_timestamp_ok: bool,
) -> tuple[list[int], str]:
    if not _table_exists(conn, "identity_status"):
        raise RuntimeError("identity_status table is missing")
    if not _column_exists(conn, "track_identity", "identity_key"):
        raise RuntimeError("track_identity.identity_key is required for archive policy")
    if not _column_exists(conn, "track_identity", "enriched_at"):
        raise RuntimeError("track_identity.enriched_at is required for archive policy")

    merged_where = "ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else "1=1"
    ts_expr, ts_source = _timestamp_expr_for_archiving(conn)
    if ts_expr is None and not no_timestamp_ok:
        raise RuntimeError(
            "archive refused: no identity timestamp columns found; rerun with --archive-orphans-no-timestamp-ok"
        )

    where_parts = [
        "ist.status = 'orphan'",
        merged_where,
        "(ti.enriched_at IS NULL OR TRIM(ti.enriched_at) = '')",
        "ti.identity_key NOT LIKE 'unidentified:%'",
    ]
    params: list[object] = []
    if ts_expr is not None:
        where_parts.append(f"julianday({ts_expr}) <= julianday('now') - ?")
        params.append(int(threshold_days))

    where_sql = " AND ".join(where_parts)
    rows = conn.execute(
        f"""
        SELECT ti.id AS identity_id
        FROM track_identity ti
        JOIN identity_status ist ON ist.identity_id = ti.id
        WHERE {where_sql}
        ORDER BY ti.id ASC
        """,
        tuple(params),
    ).fetchall()
    return [int(row["identity_id"]) for row in rows], ts_source


def _archive_orphans(
    conn: sqlite3.Connection,
    *,
    version: int,
    threshold_days: int,
    no_timestamp_ok: bool,
    execute: bool,
) -> dict[str, object]:
    candidate_ids, ts_source = _archive_candidate_ids(
        conn,
        threshold_days=int(threshold_days),
        no_timestamp_ok=bool(no_timestamp_ok),
    )
    archived = 0
    if execute and candidate_ids:
        reason_json = json.dumps(
            {
                "computed_by": "archive_orphans_policy",
                "policy": "orphan_non_enriched_non_unidentified",
                "threshold_days": int(threshold_days),
                "timestamp_source": ts_source,
                "no_timestamp_override": 1 if no_timestamp_ok else 0,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        placeholders = ",".join("?" for _ in candidate_ids)
        conn.execute(
            f"""
            UPDATE identity_status
            SET status = 'archived',
                reason_json = ?,
                version = ?,
                computed_at = CURRENT_TIMESTAMP
            WHERE identity_id IN ({placeholders})
            """,
            (reason_json, int(version), *candidate_ids),
        )
        archived = int(conn.execute("SELECT changes()").fetchone()[0])
    return {
        "eligible": len(candidate_ids),
        "archived": archived,
        "timestamp_source": ts_source,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute v3 identity lifecycle statuses")
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write identity_status table (default is plan-only)",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="Version marker written to identity_status.version (default: 1)",
    )
    parser.add_argument("--out", type=Path, help="Optional plan CSV output path")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Sample row cap for terminal/CSV output (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--archive-orphans",
        action="store_true",
        help="Archive eligible orphan identities (execute mode only)",
    )
    parser.add_argument(
        "--archive-orphans-threshold-days",
        type=int,
        default=90,
        help="Archive orphan identities older than this many days (default: 90)",
    )
    parser.add_argument(
        "--archive-orphans-no-timestamp-ok",
        action="store_true",
        help="Allow archive operation without timestamp fields (no age filter)",
    )
    return parser.parse_args(argv)


def _print_orphan_samples(rows: list[dict[str, object]], limit: int) -> None:
    print(f"orphan_samples (limit={limit}):")
    orphan_rows = [row for row in rows if str(row["computed_status"]) == "orphan"]
    if not orphan_rows:
        print("  none")
        return
    for row in orphan_rows[: int(limit)]:
        print(
            "  "
            f"identity_id={row['identity_id']} "
            f"identity_key={row['identity_key']} "
            f"isrc={row['isrc']} "
            f"beatport_id={row['beatport_id']} "
            f"canonical_artist={row['canonical_artist']} "
            f"canonical_title={row['canonical_title']}"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if int(args.version) <= 0:
        print("--version must be > 0")
        return 2
    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2
    if int(args.archive_orphans_threshold_days) <= 0:
        print("--archive-orphans-threshold-days must be > 0")
        return 2

    db_path = args.db.expanduser().resolve()
    execute_mode = bool(args.execute)

    try:
        conn = _connect_rw(db_path) if execute_mode else _connect_ro(db_path)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    rows: list[dict[str, object]] = []
    write_counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
        "skipped_merged": 0,
        "written": 0,
    }
    archive_counts = {"eligible": 0, "archived": 0, "timestamp_source": "none"}
    pre_summary: dict[str, int | float] = {}
    post_summary: dict[str, int | float] = {}

    try:
        if execute_mode:
            create_schema_v3(conn)
            conn.execute("BEGIN")
            try:
                statuses = compute_identity_statuses(conn)
                write_counts = upsert_identity_statuses(conn, statuses, version=int(args.version))
                if args.archive_orphans:
                    archive_counts = _archive_orphans(
                        conn,
                        version=int(args.version),
                        threshold_days=int(args.archive_orphans_threshold_days),
                        no_timestamp_ok=bool(args.archive_orphans_no_timestamp_ok),
                        execute=True,
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

            post_summary = summary_counts(conn)
            rows = _load_effective_rows(conn)
        else:
            pre_summary = summary_counts(conn)
            if args.archive_orphans:
                archive_counts = _archive_orphans(
                    conn,
                    version=int(args.version),
                    threshold_days=int(args.archive_orphans_threshold_days),
                    no_timestamp_ok=bool(args.archive_orphans_no_timestamp_ok),
                    execute=False,
                )
            rows = _load_effective_rows(conn)
    except RuntimeError as exc:
        print(str(exc))
        return 1
    except sqlite3.DatabaseError as exc:
        print(f"failed to read v3 db: {exc}")
        return 1
    finally:
        conn.close()

    summary = post_summary if execute_mode else pre_summary
    out_path: Path | None = None
    if args.out is not None:
        out_path = _write_csv(args.out, rows, int(args.limit) if args.limit is not None else None)

    print(f"v3 db: {db_path}")
    print(f"mode: {'execute' if execute_mode else 'plan'}")
    print(f"identities_total: {int(summary['identities_total'])}")
    print(f"non_merged_identities: {int(summary['non_merged_identities'])}")
    print(f"active_identities: {int(summary['active_identities'])}")
    print(f"orphan_identities: {int(summary['orphan_identities'])}")
    print(f"archived_identities: {int(summary['archived_identities'])}")
    print(f"merged_identities: {int(summary['merged_identities'])}")
    print(f"status_rows: {int(summary['status_rows'])}")
    print(f"status_missing: {int(summary['status_missing'])}")
    print(f"status_coverage: {float(summary['status_coverage']):.4f}")

    if args.archive_orphans:
        print(f"archive_eligible: {int(archive_counts['eligible'])}")
        print(f"archive_applied: {int(archive_counts['archived'])}")
        print(f"archive_timestamp_source: {archive_counts['timestamp_source']}")

    if execute_mode:
        print(f"version: {int(args.version)}")
        print(f"rows_inserted: {write_counts['inserted']}")
        print(f"rows_updated: {write_counts['updated']}")
        print(f"rows_unchanged: {write_counts['unchanged']}")
        print(f"rows_deleted: {write_counts['deleted']}")
        print(f"rows_written: {write_counts['written']}")

    _print_orphan_samples(rows, int(args.limit))
    if out_path is not None:
        print(f"csv_out: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
