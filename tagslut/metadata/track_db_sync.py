from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PROVIDER_NAME = "rekordbox_main_db"
TRACK_FIELDS = ("genre", "bpm", "key", "label")
FILE_COLUMN_BY_FIELD = {
    "genre": "canonical_genre",
    "bpm": "canonical_bpm",
    "key": "canonical_key",
    "label": "canonical_label",
}


@dataclass(frozen=True)
class DonorTrack:
    location: str
    genre: str | None
    bpm: float | None
    key: str | None
    label: str | None


@dataclass(frozen=True)
class FileUpdateRow:
    path: str
    dj_pool_path: str
    applied_fields: tuple[str, ...]


@dataclass(frozen=True)
class IdentityUpdateRow:
    identity_id: int
    applied_fields: tuple[str, ...]


@dataclass(frozen=True)
class TrackDbSyncResult:
    matched_files: int
    donor_tracks: int
    files_considered: int
    file_rows_updated: int
    file_fields_written: int
    identity_rows_updated: int
    identity_fields_written: int
    identity_field_conflicts: dict[str, int]
    file_updates: list[FileUpdateRow]
    identity_updates: list[IdentityUpdateRow]


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _append_provider(existing: Any, provider_name: str) -> str:
    providers: list[str] = []
    if existing is not None:
        if isinstance(existing, str):
            text = existing.strip()
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = text.split(",")
                if isinstance(parsed, list):
                    providers = [str(item).strip() for item in parsed if str(item).strip()]
                else:
                    providers = [str(parsed).strip()]
        elif isinstance(existing, list):
            providers = [str(item).strip() for item in existing if str(item).strip()]
        else:
            text = str(existing).strip()
            if text:
                providers = [text]
    if provider_name not in providers:
        providers.append(provider_name)
    return json.dumps(providers, ensure_ascii=False)


def _missing_text(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.lower() in {"unknown", "n/a", "none"}


def _missing_number(value: Any) -> bool:
    if value is None:
        return True
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return True


def _normalize_text(value: Any) -> str | None:
    if _missing_text(value):
        return None
    return str(value).strip()


def _normalize_bpm(value: Any) -> float | None:
    if _missing_number(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_missing(field: str, value: Any) -> bool:
    if field == "bpm":
        return _missing_number(value)
    return _missing_text(value)


def _load_donor_tracks(
    donor_conn: sqlite3.Connection,
    *,
    donor_location_like: str,
) -> dict[str, DonorTrack]:
    donor_conn.row_factory = sqlite3.Row
    rows = donor_conn.execute(
        """
        SELECT location, genre, bpm, key, label
        FROM Track
        WHERE location LIKE ?
        """,
        (donor_location_like,),
    ).fetchall()
    return {
        str(row["location"]): DonorTrack(
            location=str(row["location"]),
            genre=_normalize_text(row["genre"]),
            bpm=_normalize_bpm(row["bpm"]),
            key=_normalize_text(row["key"]),
            label=_normalize_text(row["label"]),
        )
        for row in rows
        if _normalize_text(row["location"]) is not None
    }


def sync_v3_from_track_db(
    conn: sqlite3.Connection,
    donor_conn: sqlite3.Connection,
    *,
    donor_location_like: str = "/Volumes/MUSIC/DJ_LIBRARY/%",
    match_field: str = "dj_pool_path",
    provider_name: str = PROVIDER_NAME,
    execute: bool = False,
) -> TrackDbSyncResult:
    if match_field not in {"dj_pool_path", "path"}:
        raise ValueError(f"Unsupported match field: {match_field}")

    conn.row_factory = sqlite3.Row
    donor_tracks = _load_donor_tracks(donor_conn, donor_location_like=donor_location_like)

    active_clause = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    merged_clause = "AND ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    rows = conn.execute(
        f"""
        SELECT
            f.path,
            f.dj_pool_path,
            f.enrichment_providers,
            f.canonical_genre,
            f.canonical_bpm,
            f.canonical_key,
            f.canonical_label,
            af.id AS asset_id,
            al.identity_id,
            ti.canonical_genre AS ti_canonical_genre,
            ti.canonical_bpm AS ti_canonical_bpm,
            ti.canonical_key AS ti_canonical_key,
            ti.canonical_label AS ti_canonical_label
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al ON al.asset_id = af.id {active_clause}
        LEFT JOIN track_identity ti ON ti.id = al.identity_id {merged_clause}
        WHERE f.{match_field} LIKE ?
        """,
        (donor_location_like,),
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    file_updates: list[FileUpdateRow] = []
    identity_updates: list[IdentityUpdateRow] = []
    identity_candidates: dict[int, dict[str, set[Any]]] = {}
    identity_current: dict[int, dict[str, Any]] = {}
    matched_files = 0
    file_rows_updated = 0
    file_fields_written = 0

    started_transaction = False
    if execute and not conn.in_transaction:
        conn.execute("BEGIN")
        started_transaction = True

    try:
        for row in rows:
            match_value = row[match_field]
            donor = donor_tracks.get(str(match_value)) if match_value else None
            if donor is None:
                continue
            matched_files += 1

            pending_file: dict[str, Any] = {}
            for field in TRACK_FIELDS:
                donor_value = getattr(donor, field)
                if _value_missing(field, donor_value):
                    continue
                file_column = FILE_COLUMN_BY_FIELD[field]
                if _value_missing(field, row[file_column]):
                    pending_file[file_column] = donor_value

            if pending_file:
                provider_value = _append_provider(row["enrichment_providers"], provider_name)
                params = list(pending_file.values()) + [now, provider_value, str(row["path"])]
                assignments = [f"{column} = ?" for column in pending_file]
                assignments.extend(["enriched_at = ?", "enrichment_providers = ?"])
                if execute:
                    conn.execute(
                        f"UPDATE files SET {', '.join(assignments)} WHERE path = ?",
                        params,
                    )
                file_rows_updated += 1
                file_fields_written += len(pending_file)
                file_updates.append(
                    FileUpdateRow(
                        path=str(row["path"]),
                        dj_pool_path=str(row["dj_pool_path"] or ""),
                        applied_fields=tuple(
                            field for field, column in FILE_COLUMN_BY_FIELD.items() if column in pending_file
                        ),
                    )
                )

            identity_id = row["identity_id"]
            if identity_id is None:
                continue
            identity_id = int(identity_id)
            candidate_fields = identity_candidates.setdefault(identity_id, {field: set() for field in TRACK_FIELDS})
            current = identity_current.setdefault(
                identity_id,
                {
                    "genre": row["ti_canonical_genre"],
                    "bpm": row["ti_canonical_bpm"],
                    "key": row["ti_canonical_key"],
                    "label": row["ti_canonical_label"],
                },
            )
            for field in TRACK_FIELDS:
                donor_value = getattr(donor, field)
                if _value_missing(field, donor_value):
                    continue
                if _value_missing(field, current[field]):
                    candidate_fields[field].add(donor_value)

        identity_rows_updated = 0
        identity_fields_written = 0
        identity_field_conflicts = {field: 0 for field in TRACK_FIELDS}
        for identity_id, fields_map in identity_candidates.items():
            pending_identity: dict[str, Any] = {}
            for field, values in fields_map.items():
                if not values:
                    continue
                if len(values) > 1:
                    identity_field_conflicts[field] += 1
                    continue
                pending_identity[FILE_COLUMN_BY_FIELD[field]] = next(iter(values))
            if not pending_identity:
                continue
            pending_identity["enriched_at"] = now
            pending_identity["updated_at"] = now
            if execute:
                params = list(pending_identity.values()) + [identity_id]
                assignments = [f"{column} = ?" for column in pending_identity]
                conn.execute(
                    f"UPDATE track_identity SET {', '.join(assignments)} WHERE id = ?",
                    params,
                )
            identity_rows_updated += 1
            identity_fields_written += len(pending_identity) - 2
            identity_updates.append(
                IdentityUpdateRow(
                    identity_id=identity_id,
                    applied_fields=tuple(
                        field for field, column in FILE_COLUMN_BY_FIELD.items() if column in pending_identity
                    ),
                )
            )

        if execute and started_transaction:
            conn.commit()
    except Exception:
        if execute and started_transaction:
            conn.rollback()
        raise

    return TrackDbSyncResult(
        matched_files=matched_files,
        donor_tracks=len(donor_tracks),
        files_considered=len(rows),
        file_rows_updated=file_rows_updated,
        file_fields_written=file_fields_written,
        identity_rows_updated=identity_rows_updated,
        identity_fields_written=identity_fields_written,
        identity_field_conflicts=identity_field_conflicts,
        file_updates=file_updates,
        identity_updates=identity_updates,
    )
