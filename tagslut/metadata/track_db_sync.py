from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
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
    title: str | None
    artist: str | None
    album: str | None
    genre: str | None
    bpm: float | None
    key: str | None
    label: str | None


@dataclass(frozen=True)
class FileUpdateRow:
    path: str
    dj_pool_path: str
    match_mode: str
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
    file_field_conflicts: dict[str, int]
    match_mode_counts: dict[str, int]
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


def _normalize_lookup_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _lookup_key(title: Any, artist: Any, album: Any) -> tuple[str, str, str]:
    return (
        _normalize_lookup_text(title),
        _normalize_lookup_text(artist),
        _normalize_lookup_text(album),
    )


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
        SELECT location, title, artist, albumTitle, genre, bpm, key, label
        FROM Track
        WHERE location LIKE ?
        """,
        (donor_location_like,),
    ).fetchall()
    return {
        str(row["location"]): DonorTrack(
            location=str(row["location"]),
            title=_normalize_text(row["title"]),
            artist=_normalize_text(row["artist"]),
            album=_normalize_text(row["albumTitle"]),
            genre=_normalize_text(row["genre"]),
            bpm=_normalize_bpm(row["bpm"]),
            key=_normalize_text(row["key"]),
            label=_normalize_text(row["label"]),
        )
        for row in rows
        if _normalize_text(row["location"]) is not None
    }


def _build_donor_lookup(donor_tracks: dict[str, DonorTrack]) -> dict[tuple[str, str, str], list[DonorTrack]]:
    lookup: dict[tuple[str, str, str], list[DonorTrack]] = defaultdict(list)
    for donor in donor_tracks.values():
        key = _lookup_key(donor.title, donor.artist, donor.album)
        if any(key):
            lookup[key].append(donor)
    return lookup


def _resolve_consensus_values(donors: list[DonorTrack]) -> tuple[dict[str, Any], set[str]]:
    consensus: dict[str, Any] = {}
    conflicts: set[str] = set()
    for field in TRACK_FIELDS:
        values = []
        for donor in donors:
            value = getattr(donor, field)
            if _value_missing(field, value):
                continue
            values.append(value)
        if not values:
            continue
        unique_values = {value for value in values}
        if len(unique_values) == 1:
            consensus[field] = values[0]
        else:
            conflicts.add(field)
    return consensus, conflicts


def _row_lookup_key(row: sqlite3.Row) -> tuple[str, str, str]:
    return _lookup_key(
        row["ti_canonical_title"] or row["canonical_title"],
        row["ti_canonical_artist"] or row["canonical_artist"],
        row["ti_canonical_album"] or row["canonical_album"],
    )


def sync_v3_from_track_db(
    conn: sqlite3.Connection,
    donor_conn: sqlite3.Connection,
    *,
    donor_location_like: str = "/Volumes/MUSIC/DJ_LIBRARY/%",
    match_field: str = "dj_pool_path",
    match_mode: str = "exact_path",
    provider_name: str = PROVIDER_NAME,
    execute: bool = False,
) -> TrackDbSyncResult:
    if match_field not in {"dj_pool_path", "path"}:
        raise ValueError(f"Unsupported match field: {match_field}")
    if match_mode not in {"exact_path", "normalized_taa", "both"}:
        raise ValueError(f"Unsupported match mode: {match_mode}")

    conn.row_factory = sqlite3.Row
    donor_tracks = _load_donor_tracks(donor_conn, donor_location_like=donor_location_like)
    donor_lookup = _build_donor_lookup(donor_tracks)

    active_clause = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    merged_clause = "AND ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    rows = conn.execute(
        f"""
        SELECT
            f.path,
            f.dj_pool_path,
            f.enrichment_providers,
            f.canonical_title,
            f.canonical_artist,
            f.canonical_album,
            f.canonical_genre,
            f.canonical_bpm,
            f.canonical_key,
            f.canonical_label,
            af.id AS asset_id,
            al.identity_id,
            ti.canonical_title AS ti_canonical_title,
            ti.canonical_artist AS ti_canonical_artist,
            ti.canonical_album AS ti_canonical_album,
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
    match_mode_counts: Counter[str] = Counter()
    file_field_conflicts = {field: 0 for field in TRACK_FIELDS}

    started_transaction = False
    if execute and not conn.in_transaction:
        conn.execute("BEGIN")
        started_transaction = True

    try:
        for row in rows:
            donors: list[DonorTrack] = []
            matched_by = ""
            if match_mode in {"exact_path", "both"}:
                match_value = row[match_field]
                donor = donor_tracks.get(str(match_value)) if match_value else None
                if donor is not None:
                    donors = [donor]
                    matched_by = "exact_path"
            if not donors and match_mode in {"normalized_taa", "both"}:
                lookup_key = _row_lookup_key(row)
                if any(lookup_key):
                    donors = donor_lookup.get(lookup_key, [])
                    if donors:
                        matched_by = "normalized_taa"
            if not donors:
                continue
            matched_files += 1
            match_mode_counts[matched_by] += 1
            consensus_values, conflicts = _resolve_consensus_values(donors)
            for field in conflicts:
                file_field_conflicts[field] += 1

            pending_file: dict[str, Any] = {}
            for field in TRACK_FIELDS:
                donor_value = consensus_values.get(field)
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
                        match_mode=matched_by,
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
                donor_value = consensus_values.get(field)
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
        file_field_conflicts=file_field_conflicts,
        match_mode_counts=dict(match_mode_counts),
        file_updates=file_updates,
        identity_updates=identity_updates,
    )
