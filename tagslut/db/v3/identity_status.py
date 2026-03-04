"""Identity lifecycle status helpers for standalone v3 databases."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


ALLOWED_IDENTITY_STATUSES = ("active", "orphan", "archived")


@dataclass(frozen=True)
class IdentityStatusRow:
    identity_id: int
    identity_key: str
    merged_into_id: int | None
    asset_count: int
    computed_status: str
    reason_json: str


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


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "al.active = 1"
    return "1=1"


def _non_merged_identity_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not _table_exists(conn, "track_identity"):
        raise RuntimeError("track_identity table is missing")
    if not _table_exists(conn, "asset_link"):
        raise RuntimeError("asset_link table is missing")

    has_merged_into = _column_exists(conn, "track_identity", "merged_into_id")
    merged_select = "ti.merged_into_id AS merged_into_id" if has_merged_into else "NULL AS merged_into_id"
    merged_where = "ti.merged_into_id IS NULL" if has_merged_into else "1=1"
    active_link_where = _active_link_where(conn)

    return conn.execute(
        f"""
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            {merged_select},
            COUNT(DISTINCT CASE WHEN {active_link_where} THEN al.asset_id END) AS asset_count
        FROM track_identity ti
        LEFT JOIN asset_link al ON al.identity_id = ti.id
        WHERE {merged_where}
        GROUP BY ti.id, ti.identity_key, merged_into_id
        ORDER BY ti.id ASC
        """
    ).fetchall()


def compute_identity_statuses(conn: sqlite3.Connection) -> list[IdentityStatusRow]:
    """Compute lifecycle statuses for non-merged identities."""
    rows = _non_merged_identity_rows(conn)
    out: list[IdentityStatusRow] = []
    for row in rows:
        asset_count = int(row["asset_count"] or 0)
        computed_status = "active" if asset_count > 0 else "orphan"
        reason_json = json.dumps(
            {"computed_by": "asset_link_presence", "asset_count": asset_count},
            sort_keys=True,
            separators=(",", ":"),
        )
        merged_into_raw = row["merged_into_id"]
        merged_into_id = int(merged_into_raw) if merged_into_raw is not None else None
        out.append(
            IdentityStatusRow(
                identity_id=int(row["identity_id"]),
                identity_key=str(row["identity_key"] or ""),
                merged_into_id=merged_into_id,
                asset_count=asset_count,
                computed_status=computed_status,
                reason_json=reason_json,
            )
        )
    return out


def upsert_identity_statuses(
    conn: sqlite3.Connection,
    statuses: list[IdentityStatusRow],
    *,
    version: int,
) -> dict[str, int]:
    """Upsert computed identity statuses for non-merged identities."""
    if int(version) <= 0:
        raise RuntimeError("version must be > 0")
    if not _table_exists(conn, "identity_status"):
        raise RuntimeError("identity_status table missing; run create_schema_v3 in execute mode")

    deleted = 0
    if _column_exists(conn, "track_identity", "merged_into_id"):
        conn.execute(
            """
            DELETE FROM identity_status
            WHERE identity_id IN (
                SELECT id FROM track_identity WHERE merged_into_id IS NOT NULL
            )
            """
        )
        deleted = int(conn.execute("SELECT changes()").fetchone()[0])

    inserted = 0
    updated = 0
    unchanged = 0
    skipped_merged = 0

    for status_row in statuses:
        if status_row.merged_into_id is not None:
            skipped_merged += 1
            continue
        if status_row.computed_status not in {"active", "orphan"}:
            raise RuntimeError(f"invalid computed status: {status_row.computed_status}")

        existing = conn.execute(
            """
            SELECT status, reason_json, version
            FROM identity_status
            WHERE identity_id = ?
            """,
            (int(status_row.identity_id),),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO identity_status (
                    identity_id,
                    status,
                    reason_json,
                    version,
                    computed_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    int(status_row.identity_id),
                    status_row.computed_status,
                    status_row.reason_json,
                    int(version),
                ),
            )
            inserted += 1
            continue

        should_update = (
            str(existing["status"]) != status_row.computed_status
            or str(existing["reason_json"]) != status_row.reason_json
            or int(existing["version"]) != int(version)
        )
        if should_update:
            conn.execute(
                """
                UPDATE identity_status
                SET status = ?,
                    reason_json = ?,
                    version = ?,
                    computed_at = CURRENT_TIMESTAMP
                WHERE identity_id = ?
                """,
                (
                    status_row.computed_status,
                    status_row.reason_json,
                    int(version),
                    int(status_row.identity_id),
                ),
            )
            updated += 1
        else:
            unchanged += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "deleted": deleted,
        "skipped_merged": skipped_merged,
        "written": inserted + updated,
    }


def summary_counts(conn: sqlite3.Connection) -> dict[str, int | float]:
    """Return lifecycle and coverage counts for the current DB snapshot."""
    if not _table_exists(conn, "track_identity"):
        raise RuntimeError("track_identity table is missing")
    if not _table_exists(conn, "asset_link"):
        raise RuntimeError("asset_link table is missing")

    has_merged_into = _column_exists(conn, "track_identity", "merged_into_id")
    has_status_table = _table_exists(conn, "identity_status")
    active_link_where = _active_link_where(conn)

    rows: list[sqlite3.Row]
    if has_status_table:
        merged_select = "ti.merged_into_id AS merged_into_id" if has_merged_into else "NULL AS merged_into_id"
        rows = conn.execute(
            f"""
            SELECT
                ti.id AS identity_id,
                {merged_select},
                ist.status AS stored_status,
                COUNT(DISTINCT CASE WHEN {active_link_where} THEN al.asset_id END) AS asset_count
            FROM track_identity ti
            LEFT JOIN asset_link al ON al.identity_id = ti.id
            LEFT JOIN identity_status ist ON ist.identity_id = ti.id
            GROUP BY ti.id, merged_into_id, ist.status
            ORDER BY ti.id ASC
            """
        ).fetchall()
    else:
        merged_select = "ti.merged_into_id AS merged_into_id" if has_merged_into else "NULL AS merged_into_id"
        rows = conn.execute(
            f"""
            SELECT
                ti.id AS identity_id,
                {merged_select},
                '' AS stored_status,
                COUNT(DISTINCT CASE WHEN {active_link_where} THEN al.asset_id END) AS asset_count
            FROM track_identity ti
            LEFT JOIN asset_link al ON al.identity_id = ti.id
            GROUP BY ti.id, merged_into_id
            ORDER BY ti.id ASC
            """
        ).fetchall()

    merged = 0
    active = 0
    orphan = 0
    archived = 0
    non_merged = 0
    status_rows = 0

    for row in rows:
        merged_into_raw = row["merged_into_id"]
        merged_into_id = int(merged_into_raw) if merged_into_raw is not None else None
        stored_status = str(row["stored_status"] or "")
        asset_count = int(row["asset_count"] or 0)

        if merged_into_id is not None:
            merged += 1
            continue

        non_merged += 1
        if stored_status in ALLOWED_IDENTITY_STATUSES:
            status_rows += 1

        if stored_status == "archived":
            archived += 1
        elif asset_count > 0:
            active += 1
        else:
            orphan += 1

    total = len(rows)
    status_missing = max(non_merged - status_rows, 0)
    status_coverage = float(status_rows / non_merged) if non_merged > 0 else 1.0
    return {
        "identities_total": total,
        "non_merged_identities": non_merged,
        "merged_identities": merged,
        "active_identities": active,
        "orphan_identities": orphan,
        "archived_identities": archived,
        "status_rows": status_rows,
        "status_missing": status_missing,
        "status_coverage": status_coverage,
    }
