"""Identity merge helpers for standalone v3 databases."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

CANONICAL_FIELDS = (
    "canonical_title",
    "canonical_artist",
    "canonical_album",
    "canonical_genre",
    "canonical_sub_genre",
    "canonical_label",
    "canonical_catalog_number",
    "canonical_mix_name",
    "canonical_duration",
    "canonical_year",
    "canonical_release_date",
    "canonical_bpm",
    "canonical_key",
    "canonical_payload_json",
)


@dataclass(frozen=True)
class Group:
    beatport_id: str
    identity_ids: tuple[int, ...]


@dataclass(frozen=True)
class CandidateScore:
    identity_id: int
    score: int
    has_enriched_at: bool
    has_core_fields: bool
    has_isrc: bool
    asset_count: int


@dataclass(frozen=True)
class WinnerSelection:
    winner_id: int
    rationale: str
    candidate_scores: tuple[CandidateScore, ...]


@dataclass(frozen=True)
class MergeResult:
    merge_type: str
    key_value: str
    winner_identity_id: int
    loser_identity_ids: tuple[int, ...]
    assets_moved: int
    fields_copied: dict[str, Any]
    rationale: dict[str, Any]
    dry_run: bool


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


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _active_identity_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "track_identity", "merged_into_id"):
        return "merged_into_id IS NULL"
    return "1=1"


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "active = 1"
    return "1=1"


def _normalize_ids(identity_ids: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    normalized = sorted({int(identity_id) for identity_id in identity_ids})
    if not normalized:
        raise RuntimeError("identity_ids must not be empty")
    return tuple(normalized)


def _identity_rows_by_id(
    conn: sqlite3.Connection, identity_ids: tuple[int, ...]
) -> dict[int, sqlite3.Row]:
    placeholders = ",".join("?" for _ in identity_ids)
    select_columns = [
        "id",
        "identity_key",
        "beatport_id",
        "merged_into_id" if _column_exists(conn, "track_identity", "merged_into_id") else "NULL AS merged_into_id",
        "isrc",
        "canonical_artist",
        "canonical_title",
        "enriched_at",
    ]
    for field in CANONICAL_FIELDS:
        if field in select_columns:
            continue
        if _column_exists(conn, "track_identity", field):
            select_columns.append(field)
        else:
            select_columns.append(f"NULL AS {field}")
    rows = conn.execute(
        f"""
        SELECT
            {', '.join(select_columns)}
        FROM track_identity
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(identity_ids),
    ).fetchall()
    out = {int(row["id"]): row for row in rows}
    if len(out) != len(identity_ids):
        missing = sorted(set(identity_ids) - set(out.keys()))
        raise RuntimeError(f"identity rows not found: {missing}")
    return out


def _asset_counts_by_identity(
    conn: sqlite3.Connection, identity_ids: tuple[int, ...]
) -> dict[int, int]:
    placeholders = ",".join("?" for _ in identity_ids)
    where_active = _active_link_where(conn)
    rows = conn.execute(
        f"""
        SELECT identity_id, COUNT(*) AS asset_count
        FROM asset_link
        WHERE identity_id IN ({placeholders}) AND {where_active}
        GROUP BY identity_id
        """,
        tuple(identity_ids),
    ).fetchall()
    out = {int(row["identity_id"]): int(row["asset_count"]) for row in rows}
    for identity_id in identity_ids:
        out.setdefault(int(identity_id), 0)
    return out


def _existing_canonical_fields(conn: sqlite3.Connection) -> tuple[str, ...]:
    fields: list[str] = []
    for field in CANONICAL_FIELDS:
        if _column_exists(conn, "track_identity", field):
            fields.append(field)
    return tuple(fields)


def _candidate_to_dict(candidate: CandidateScore) -> dict[str, Any]:
    return {
        "identity_id": candidate.identity_id,
        "score": candidate.score,
        "has_enriched_at": int(candidate.has_enriched_at),
        "has_core_fields": int(candidate.has_core_fields),
        "has_isrc": int(candidate.has_isrc),
        "asset_count": candidate.asset_count,
    }


def _assert_foreign_keys_on(conn: sqlite3.Connection) -> None:
    fk_enabled = int(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    if fk_enabled != 1:
        raise RuntimeError("foreign_keys must be ON")


def _assert_asset_link_unique(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        """
        SELECT asset_id, COUNT(*) AS n
        FROM asset_link
        GROUP BY asset_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        raise RuntimeError(
            f"asset_link uniqueness violated: asset_id={int(row['asset_id'])} has {int(row['n'])} rows"
        )


def _assert_active_links_resolve_to_canonical(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "track_identity", "merged_into_id"):
        return
    where_active = _active_link_where(conn)
    row = conn.execute(
        f"""
        SELECT al.asset_id, al.identity_id, ti.merged_into_id
        FROM asset_link al
        JOIN track_identity ti ON ti.id = al.identity_id
        WHERE {where_active}
          AND ti.merged_into_id IS NOT NULL
        LIMIT 1
        """
    ).fetchone()
    if row is not None:
        raise RuntimeError(
            "active asset_link points to merged identity: "
            f"asset_id={int(row['asset_id'])} identity_id={int(row['identity_id'])} "
            f"merged_into_id={int(row['merged_into_id'])}"
        )


def _assert_merge_lineage(
    conn: sqlite3.Connection,
    winner_id: int,
    loser_ids: tuple[int, ...],
) -> None:
    if not _column_exists(conn, "track_identity", "merged_into_id"):
        return
    ids = (int(winner_id), *tuple(int(identity_id) for identity_id in loser_ids))
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT id, merged_into_id
        FROM track_identity
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        ids,
    ).fetchall()
    row_by_id = {int(row["id"]): row for row in rows}

    winner_row = row_by_id.get(int(winner_id))
    if winner_row is None:
        raise RuntimeError(f"winner identity missing after merge: {winner_id}")
    if winner_row["merged_into_id"] is not None:
        raise RuntimeError(
            f"winner identity must remain active after merge: winner_id={winner_id} "
            f"merged_into_id={int(winner_row['merged_into_id'])}"
        )

    for loser_id in loser_ids:
        loser_row = row_by_id.get(int(loser_id))
        if loser_row is None:
            raise RuntimeError(f"loser identity missing after merge: {loser_id}")
        merged_into = loser_row["merged_into_id"]
        if merged_into is None or int(merged_into) != int(winner_id):
            raise RuntimeError(
                f"loser identity does not resolve to winner after merge: "
                f"loser_id={int(loser_id)} winner_id={winner_id} merged_into_id={merged_into!r}"
            )


def _sync_legacy_file_keys(
    conn: sqlite3.Connection, winner_key: str, loser_keys: tuple[str, ...]
) -> None:
    if not _table_exists(conn, "files"):
        return
    if not _column_exists(conn, "files", "library_track_key"):
        return
    if not loser_keys:
        return
    placeholders = ",".join("?" for _ in loser_keys)
    conn.execute(
        f"""
        UPDATE files
        SET library_track_key = ?
        WHERE library_track_key IN ({placeholders})
        """,
        (winner_key, *loser_keys),
    )


def find_duplicate_beatport_groups(conn: sqlite3.Connection) -> list[Group]:
    """Return duplicate beatport_id groups among active identities."""
    if not _table_exists(conn, "track_identity"):
        return []
    if not _column_exists(conn, "track_identity", "beatport_id"):
        return []

    where_active = _active_identity_where(conn)
    rows = conn.execute(
        f"""
        SELECT id, TRIM(beatport_id) AS beatport_id
        FROM track_identity
        WHERE beatport_id IS NOT NULL
          AND TRIM(beatport_id) != ''
          AND {where_active}
        ORDER BY beatport_id ASC, id ASC
        """
    ).fetchall()

    grouped: dict[str, list[int]] = {}
    for row in rows:
        beatport_id = str(row["beatport_id"])
        grouped.setdefault(beatport_id, []).append(int(row["id"]))

    out: list[Group] = []
    for beatport_id in sorted(grouped):
        ids = grouped[beatport_id]
        if len(ids) > 1:
            out.append(Group(beatport_id=beatport_id, identity_ids=tuple(ids)))
    return out


def choose_winner_identity(
    conn: sqlite3.Connection, identity_ids: list[int] | tuple[int, ...]
) -> WinnerSelection:
    """Choose a deterministic winner for one duplicate identity group."""
    normalized_ids = _normalize_ids(identity_ids)
    rows_by_id = _identity_rows_by_id(conn, normalized_ids)
    counts_by_id = _asset_counts_by_identity(conn, normalized_ids)

    candidates: list[CandidateScore] = []
    for identity_id in normalized_ids:
        row = rows_by_id[identity_id]
        has_enriched_at = not _is_blank(row["enriched_at"])
        has_core_fields = not _is_blank(row["canonical_artist"]) and not _is_blank(
            row["canonical_title"]
        )
        has_isrc = not _is_blank(row["isrc"])
        asset_count = int(counts_by_id.get(identity_id, 0))

        score = 0
        if has_enriched_at:
            score += 100
        if has_core_fields:
            score += 30
        if has_isrc:
            score += 20
        score += min(asset_count, 20)

        candidates.append(
            CandidateScore(
                identity_id=identity_id,
                score=score,
                has_enriched_at=has_enriched_at,
                has_core_fields=has_core_fields,
                has_isrc=has_isrc,
                asset_count=asset_count,
            )
        )

    ordered = sorted(candidates, key=lambda c: (-c.score, c.identity_id))
    winner = ordered[0]
    rationale = (
        "winner selected by score "
        "(enriched_at=+100, core_fields=+30, isrc=+20, asset_count=+min(count,20)); "
        f"tie-breaker lowest id -> {winner.identity_id}"
    )
    return WinnerSelection(
        winner_id=winner.identity_id,
        rationale=rationale,
        candidate_scores=tuple(ordered),
    )


def merge_group_by_repointing_assets(
    conn: sqlite3.Connection,
    winner_id: int,
    loser_ids: list[int] | tuple[int, ...],
    *,
    dry_run: bool,
) -> MergeResult:
    """Merge one duplicate identity group by repointing asset_link rows."""
    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")

    try:
        normalized_losers = _normalize_ids(loser_ids)
        if int(winner_id) in normalized_losers:
            raise RuntimeError("winner_id cannot be included in loser_ids")

        _assert_foreign_keys_on(conn)

        all_ids = tuple(sorted({int(winner_id), *normalized_losers}))
        rows_by_id = _identity_rows_by_id(conn, all_ids)
        winner_row = rows_by_id[int(winner_id)]
        if _column_exists(conn, "track_identity", "merged_into_id") and winner_row["merged_into_id"] is not None:
            raise RuntimeError("winner identity cannot already be merged")

        beatport_id = str(winner_row["beatport_id"] or "").strip()
        if not beatport_id:
            raise RuntimeError("winner identity must have non-empty beatport_id")

        selection = choose_winner_identity(conn, all_ids)
        if selection.winner_id != int(winner_id):
            raise RuntimeError(
                f"winner mismatch: expected {winner_id}, deterministic selector chose {selection.winner_id}"
            )

        loser_placeholders = ",".join("?" for _ in normalized_losers)
        where_active_link = _active_link_where(conn)
        assets_moved_row = conn.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM asset_link
            WHERE identity_id IN ({loser_placeholders}) AND {where_active_link}
            """,
            tuple(normalized_losers),
        ).fetchone()
        assets_moved = int(assets_moved_row["n"]) if assets_moved_row else 0

        existing_fields = _existing_canonical_fields(conn)
        fields_copied: dict[str, Any] = {}
        loser_keys = tuple(str(rows_by_id[int(loser_id)]["identity_key"]) for loser_id in normalized_losers)
        for field in existing_fields:
            winner_value = winner_row[field]
            if not _is_blank(winner_value):
                continue
            for loser_id in normalized_losers:
                loser_value = rows_by_id[int(loser_id)][field]
                if not _is_blank(loser_value):
                    fields_copied[field] = loser_value
                    break
        if _column_exists(conn, "track_identity", "isrc") and _is_blank(winner_row["isrc"]):
            for loser_id in normalized_losers:
                loser_isrc = rows_by_id[int(loser_id)]["isrc"]
                if not _is_blank(loser_isrc):
                    fields_copied["isrc"] = loser_isrc
                    break

        if _column_exists(conn, "track_identity", "merged_into_id"):
            for loser_id in normalized_losers:
                if rows_by_id[int(loser_id)]["merged_into_id"] is not None:
                    raise RuntimeError(f"loser identity is already merged: {int(loser_id)}")

        if not dry_run:
            conn.execute(
                f"""
                UPDATE asset_link
                SET identity_id = ?
                WHERE identity_id IN ({loser_placeholders})
                """,
                (int(winner_id), *normalized_losers),
            )

            if fields_copied:
                set_clause = ", ".join(f"{field} = ?" for field in fields_copied)
                params: list[Any] = list(fields_copied.values())
                params.append(int(winner_id))
                conn.execute(
                    f"""
                    UPDATE track_identity
                    SET {set_clause}
                    WHERE id = ?
                    """,
                    tuple(params),
                )

            if _column_exists(conn, "track_identity", "merged_into_id"):
                conn.execute(
                    f"""
                    UPDATE track_identity
                    SET merged_into_id = ?
                    WHERE id IN ({loser_placeholders})
                    """,
                    (int(winner_id), *normalized_losers),
                )
                conn.execute(
                    f"""
                    UPDATE track_identity
                    SET beatport_id = NULL
                    WHERE id IN ({loser_placeholders})
                      AND merged_into_id = ?
                    """,
                    (*normalized_losers, int(winner_id)),
                )
                _sync_legacy_file_keys(
                    conn,
                    str(winner_row["identity_key"]),
                    loser_keys,
                )
                if _table_exists(conn, "preferred_asset"):
                    conn.execute(
                        f"""
                        DELETE FROM preferred_asset
                        WHERE identity_id IN ({loser_placeholders})
                        """,
                        tuple(normalized_losers),
                    )
                from tagslut.storage.v3.identity_service import mirror_identity_to_legacy

                mirror_identity_to_legacy(conn, int(winner_id), asset_id=None)

        if not dry_run:
            where_active_identity = _active_identity_where(conn)
            duplicate_row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM track_identity
                WHERE beatport_id = ? AND {where_active_identity}
                """,
                (beatport_id,),
            ).fetchone()
            duplicate_count = int(duplicate_row["n"]) if duplicate_row else 0
            if duplicate_count > 1:
                raise RuntimeError(
                    "duplicate beatport_id remains after merge: "
                    f"beatport_id={beatport_id} active_count={duplicate_count}"
                )

            _assert_merge_lineage(conn, int(winner_id), tuple(normalized_losers))
            _assert_asset_link_unique(conn)
            _assert_active_links_resolve_to_canonical(conn)
            _assert_foreign_keys_on(conn)

        rationale = {
            "winner_selection": selection.rationale,
            "candidate_scores": [
                _candidate_to_dict(candidate) for candidate in selection.candidate_scores
            ],
        }
        result = MergeResult(
            merge_type="beatport_id",
            key_value=beatport_id,
            winner_identity_id=int(winner_id),
            loser_identity_ids=tuple(int(identity_id) for identity_id in normalized_losers),
            assets_moved=assets_moved,
            fields_copied=fields_copied,
            rationale=rationale,
            dry_run=bool(dry_run),
        )
        if owns_transaction:
            conn.commit()
        return result
    except Exception:
        if owns_transaction:
            conn.rollback()
        raise


def record_identity_merge_provenance(
    conn: sqlite3.Connection, merge_result: MergeResult
) -> None:
    """Record merge details in identity_merge_log and provenance_event (if present)."""
    if not _table_exists(conn, "identity_merge_log"):
        raise RuntimeError("identity_merge_log table is missing")

    conn.execute(
        """
        INSERT INTO identity_merge_log (
            merge_type,
            key_value,
            winner_identity_id,
            loser_identity_ids,
            assets_moved,
            fields_copied_json,
            rationale_json,
            dry_run
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            merge_result.merge_type,
            merge_result.key_value,
            int(merge_result.winner_identity_id),
            json.dumps(list(merge_result.loser_identity_ids), sort_keys=True),
            int(merge_result.assets_moved),
            json.dumps(merge_result.fields_copied, sort_keys=True),
            json.dumps(merge_result.rationale, sort_keys=True),
            1 if merge_result.dry_run else 0,
        ),
    )

    if _table_exists(conn, "provenance_event"):
        details = {
            "merge_type": merge_result.merge_type,
            "key_value": merge_result.key_value,
            "winner_identity_id": merge_result.winner_identity_id,
            "loser_identity_ids": list(merge_result.loser_identity_ids),
            "assets_moved": merge_result.assets_moved,
            "fields_copied": merge_result.fields_copied,
            "dry_run": 1 if merge_result.dry_run else 0,
            "rationale": merge_result.rationale,
        }
        conn.execute(
            """
            INSERT INTO provenance_event (
                event_type,
                identity_id,
                status,
                details_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "identity_merge",
                int(merge_result.winner_identity_id),
                "dry_run" if merge_result.dry_run else "merged",
                json.dumps(details, sort_keys=True, separators=(",", ":")),
            ),
        )
