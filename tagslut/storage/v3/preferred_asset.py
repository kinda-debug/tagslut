"""Deterministic preferred-asset selection for standalone v3 databases."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class PreferredChoice:
    identity_id: int
    identity_key: str
    asset_id: int
    chosen_path: str
    score: float
    reason_json: str


@dataclass(frozen=True)
class _Candidate:
    asset_id: int
    path: str
    score: float
    reason_parts: dict[str, Any]
    rank_tuple: tuple[int, int, int, int, int, int, float]


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


def _to_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        raw = value.decode() if isinstance(value, (bytes, bytearray)) else value
        try:
            return int(raw)
        except ValueError:
            return 0
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (str, bytes, bytearray)):
        raw = value.decode() if isinstance(value, (bytes, bytearray)) else value
        try:
            return float(raw)
        except ValueError:
            return 0.0
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def _to_bool_1(value: object) -> int:
    if value in (1, True, "1", "true", "TRUE", "yes", "YES", "ok", "OK"):
        return 1
    return 0


def _integrity_rank(value: object) -> int:
    raw = str(value or "").strip().lower()
    if raw in {"ok", "verified", "pass", "passed", "clean", "good"}:
        return 2
    if raw in {"failed", "fail", "bad", "error", "corrupt", "mismatch", "invalid"}:
        return 0
    return 1


def _active_identity_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "track_identity", "merged_into_id"):
        return "merged_into_id IS NULL"
    return "1=1"


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "active = 1"
    return "1=1"


def _asset_select_sql(conn: sqlite3.Connection) -> str:
    parts: list[str] = ["af.id AS asset_id", "af.path AS path"]
    if _column_exists(conn, "asset_file", "integrity_state"):
        parts.append("af.integrity_state AS integrity_state")
    else:
        parts.append("NULL AS integrity_state")
    if _column_exists(conn, "asset_file", "flac_ok"):
        parts.append("af.flac_ok AS flac_ok")
    else:
        parts.append("NULL AS flac_ok")
    if _column_exists(conn, "asset_file", "bit_depth"):
        parts.append("af.bit_depth AS bit_depth")
    else:
        parts.append("NULL AS bit_depth")
    if _column_exists(conn, "asset_file", "sample_rate"):
        parts.append("af.sample_rate AS sample_rate")
    else:
        parts.append("NULL AS sample_rate")
    if _column_exists(conn, "asset_file", "sha256_checked_at"):
        parts.append("af.sha256_checked_at AS sha256_checked_at")
    else:
        parts.append("NULL AS sha256_checked_at")
    if _column_exists(conn, "asset_file", "content_sha256"):
        parts.append("af.content_sha256 AS content_sha256")
    else:
        parts.append("NULL AS content_sha256")
    if _column_exists(conn, "asset_file", "size_bytes"):
        parts.append("af.size_bytes AS size_value")
    elif _column_exists(conn, "asset_file", "size"):
        parts.append("af.size AS size_value")
    else:
        parts.append("NULL AS size_value")
    if _column_exists(conn, "asset_file", "mtime"):
        parts.append("af.mtime AS mtime_value")
    else:
        parts.append("NULL AS mtime_value")
    return ", ".join(parts)


def _ensure_preferred_asset_table(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "preferred_asset"):
        raise RuntimeError("preferred_asset table missing; run create_schema_v3 in execute mode")


def _build_reason_json(
    *,
    identity_id: int,
    identity_key: str,
    winner: _Candidate,
    sorted_candidates: list[_Candidate],
) -> str:
    tie_break_reason = "single_candidate"
    if len(sorted_candidates) > 1:
        runner_up = sorted_candidates[1]
        if winner.rank_tuple == runner_up.rank_tuple:
            if winner.path != runner_up.path:
                tie_break_reason = "path_lexicographic"
            else:
                tie_break_reason = "asset_id"
        else:
            tie_break_reason = "higher_rank_tuple"

    payload = {
        "identity_id": int(identity_id),
        "identity_key": identity_key,
        "selection_order": [
            "integrity_rank",
            "flac_ok",
            "bit_depth",
            "sample_rate",
            "has_sha",
            "size_bytes",
            "mtime",
            "path",
            "asset_id",
        ],
        "final_tie_break": tie_break_reason,
        "winner": {
            "asset_id": winner.asset_id,
            "path": winner.path,
            "score": winner.score,
            **winner.reason_parts,
        },
        "candidates": [
            {
                "asset_id": candidate.asset_id,
                "path": candidate.path,
                "score": candidate.score,
                **candidate.reason_parts,
            }
            for candidate in sorted_candidates
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def compute_candidate_score(asset_row: sqlite3.Row) -> tuple[float, dict[str, Any]]:
    """Compute a deterministic candidate score and explainable reason parts."""
    integrity_state = str(asset_row["integrity_state"] or "").strip()
    integrity_rank = _integrity_rank(integrity_state)
    flac_ok = _to_bool_1(asset_row["flac_ok"])
    bit_depth = max(_to_int(asset_row["bit_depth"]), 0)
    sample_rate = max(_to_int(asset_row["sample_rate"]), 0)
    has_sha = int(
        (not _is_blank(asset_row["sha256_checked_at"]))
        or (not _is_blank(asset_row["content_sha256"]))
    )
    size_bytes = max(_to_int(asset_row["size_value"]), 0)
    mtime_value = max(_to_float(asset_row["mtime_value"]), 0.0)

    # Score preserves deterministic precedence:
    # integrity > flac_ok > bit_depth > sample_rate > has_sha > size > mtime.
    score = (
        float(integrity_rank) * 1_000_000_000.0
        + float(flac_ok) * 100_000_000.0
        + float(bit_depth) * 1_000_000.0
        + float(sample_rate) * 10.0
        + float(has_sha)
        + (min(float(size_bytes), 100_000_000_000.0) / 100_000_000_000.0)
        + (min(float(mtime_value), 10_000_000_000.0) / 10_000_000_000_000.0)
    )

    return (
        score,
        {
            "integrity_state": integrity_state,
            "integrity_rank": integrity_rank,
            "flac_ok": flac_ok,
            "bit_depth": bit_depth,
            "sample_rate": sample_rate,
            "has_sha": has_sha,
            "size_bytes": size_bytes,
            "mtime": mtime_value,
        },
    )


def choose_preferred_asset_for_identity(
    conn: sqlite3.Connection, identity_id: int
) -> PreferredChoice:
    """Choose one deterministic preferred asset for a specific identity."""
    identity_row = conn.execute(
        "SELECT id, identity_key FROM track_identity WHERE id = ?",
        (int(identity_id),),
    ).fetchone()
    if identity_row is None:
        raise RuntimeError(f"identity not found: {identity_id}")

    select_sql = _asset_select_sql(conn)
    where_active = _active_link_where(conn)
    asset_rows = conn.execute(
        f"""
        SELECT {select_sql}
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE al.identity_id = ? AND {where_active}
        ORDER BY af.id ASC
        """,
        (int(identity_id),),
    ).fetchall()

    if not asset_rows:
        raise LookupError(f"identity has no linked assets: {identity_id}")

    candidates: list[_Candidate] = []
    for row in asset_rows:
        score, reason_parts = compute_candidate_score(row)
        candidates.append(
            _Candidate(
                asset_id=int(row["asset_id"]),
                path=str(row["path"] or ""),
                score=float(score),
                reason_parts=reason_parts,
                rank_tuple=(
                    int(reason_parts["integrity_rank"]),
                    int(reason_parts["flac_ok"]),
                    int(reason_parts["bit_depth"]),
                    int(reason_parts["sample_rate"]),
                    int(reason_parts["has_sha"]),
                    int(reason_parts["size_bytes"]),
                    float(reason_parts["mtime"]),
                ),
            )
        )

    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            -c.rank_tuple[0],
            -c.rank_tuple[1],
            -c.rank_tuple[2],
            -c.rank_tuple[3],
            -c.rank_tuple[4],
            -c.rank_tuple[5],
            -c.rank_tuple[6],
            c.path,
            c.asset_id,
        ),
    )
    winner = sorted_candidates[0]

    reason_json = _build_reason_json(
        identity_id=int(identity_row["id"]),
        identity_key=str(identity_row["identity_key"] or ""),
        winner=winner,
        sorted_candidates=sorted_candidates,
    )
    return PreferredChoice(
        identity_id=int(identity_row["id"]),
        identity_key=str(identity_row["identity_key"] or ""),
        asset_id=int(winner.asset_id),
        chosen_path=winner.path,
        score=float(winner.score),
        reason_json=reason_json,
    )


def compute_preferred_assets(
    conn: sqlite3.Connection, *, limit: int | None = None
) -> Iterable[PreferredChoice]:
    """Compute preferred assets for active identities (plan mode friendly)."""
    where_active = _active_identity_where(conn)
    sql = (
        "SELECT id, identity_key FROM track_identity "
        f"WHERE {where_active} ORDER BY id ASC"
    )
    params: tuple[object, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = conn.execute(sql, params).fetchall()

    choices: list[PreferredChoice] = []
    for row in rows:
        try:
            choice = choose_preferred_asset_for_identity(conn, int(row["id"]))
        except LookupError:
            continue
        choices.append(choice)
    return choices


def upsert_preferred_assets(
    conn: sqlite3.Connection,
    choices: Iterable[PreferredChoice],
    *,
    version: int,
) -> dict[str, int]:
    """Upsert preferred assets into the materialized table."""
    _ensure_preferred_asset_table(conn)

    inserted = 0
    updated = 0
    unchanged = 0
    for choice in choices:
        existing = conn.execute(
            """
            SELECT asset_id, score, reason_json, version
            FROM preferred_asset
            WHERE identity_id = ?
            """,
            (int(choice.identity_id),),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO preferred_asset (
                    identity_id, asset_id, score, reason_json, version, computed_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    int(choice.identity_id),
                    int(choice.asset_id),
                    float(choice.score),
                    choice.reason_json,
                    int(version),
                ),
            )
            inserted += 1
            continue

        should_update = (
            int(existing["asset_id"]) != int(choice.asset_id)
            or float(existing["score"]) != float(choice.score)
            or str(existing["reason_json"]) != str(choice.reason_json)
            or int(existing["version"]) != int(version)
        )
        if should_update:
            conn.execute(
                """
                UPDATE preferred_asset
                SET asset_id = ?,
                    score = ?,
                    reason_json = ?,
                    version = ?,
                    computed_at = CURRENT_TIMESTAMP
                WHERE identity_id = ?
                """,
                (
                    int(choice.asset_id),
                    float(choice.score),
                    choice.reason_json,
                    int(version),
                    int(choice.identity_id),
                ),
            )
            updated += 1
        else:
            unchanged += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "written": inserted + updated,
    }
