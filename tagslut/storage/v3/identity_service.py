"""Identity service for v3 identity resolution."""

from __future__ import annotations

import json
import logging
import sqlite3
import re
from collections.abc import Mapping
from difflib import SequenceMatcher
from typing import Any

__all__ = [
    "resolve_active_identity",
    "resolve_or_create_identity",
    "link_asset_to_identity",
    "mirror_identity_to_legacy",
]

PROVIDER_COLUMNS: tuple[str, ...] = (
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "spotify_id",
    "apple_music_id",
    "deezer_id",
    "traxsource_id",
    "itunes_id",
    "musicbrainz_id",
)
FUZZY_DURATION_TOLERANCE_S = 2.0
FUZZY_SCORE_THRESHOLD = 0.92
logger = logging.getLogger(__name__)


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


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (list, tuple)):
        for item in value:
            normalized = _norm_text(item)
            if normalized:
                return normalized
        return None
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="replace").strip()
        return text or None
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip().lower()


def _lookup_value(mapping: Mapping[str, Any], *keys: str) -> str | None:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for key in keys:
        if key.lower() in lowered:
            value = _norm_text(lowered[key.lower()])
            if value:
                return value
    return None


def _row_value(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _norm_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _duration_seconds(asset_row: sqlite3.Row, metadata: Mapping[str, Any]) -> float | None:
    duration_ms = _lookup_value(metadata, "duration_ms", "canonical_duration_ms")
    if duration_ms:
        try:
            return float(duration_ms) / 1000.0
        except ValueError:
            pass

    for key in ("duration_s", "duration", "canonical_duration", "duration_seconds"):
        value = _lookup_value(metadata, key)
        if value:
            try:
                return float(value)
            except ValueError:
                continue

    return _to_float(_row_value(asset_row, "duration_s"))


def _duration_ref_ms(duration_s: float | None) -> int | None:
    if duration_s is None:
        return None
    return int(round(duration_s * 1000.0))


def _is_blank_db(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _identity_value_map(
    asset_row: sqlite3.Row,
    metadata: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    duration_s = _duration_seconds(asset_row, metadata)
    provider_values = {
        "beatport_id": _lookup_value(metadata, "beatport_id"),
        "tidal_id": _lookup_value(metadata, "tidal_id"),
        "qobuz_id": _lookup_value(metadata, "qobuz_id"),
        "spotify_id": _lookup_value(metadata, "spotify_id"),
        "apple_music_id": _lookup_value(metadata, "apple_music_id", "apple_music_track_id"),
        "deezer_id": _lookup_value(metadata, "deezer_id"),
        "traxsource_id": _lookup_value(metadata, "traxsource_id"),
        "itunes_id": _lookup_value(metadata, "itunes_id"),
        "musicbrainz_id": _lookup_value(metadata, "musicbrainz_id", "musicbrainz_recording_id"),
    }
    artist = _lookup_value(metadata, "artist", "canonical_artist")
    title = _lookup_value(metadata, "title", "canonical_title")
    payload_json: str | None = None
    if metadata:
        try:
            payload_json = json.dumps(dict(metadata), sort_keys=True, separators=(",", ":"))
        except TypeError:
            payload_json = None

    values: dict[str, Any] = {
        "isrc": _lookup_value(metadata, "isrc", "canonical_isrc"),
        **provider_values,
        "artist_norm": _norm_name(artist),
        "title_norm": _norm_name(title),
        "album_norm": _norm_name(_lookup_value(metadata, "album", "canonical_album")),
        "canonical_title": title,
        "canonical_artist": artist,
        "canonical_album": _lookup_value(metadata, "album", "canonical_album"),
        "canonical_genre": _lookup_value(metadata, "genre", "canonical_genre"),
        "canonical_sub_genre": _lookup_value(metadata, "sub_genre", "canonical_sub_genre"),
        "canonical_label": _lookup_value(metadata, "label", "canonical_label"),
        "canonical_catalog_number": _lookup_value(
            metadata, "catalog_number", "canonical_catalog_number"
        ),
        "canonical_mix_name": _lookup_value(metadata, "mix_name", "canonical_mix_name"),
        "canonical_duration": duration_s,
        "canonical_year": _lookup_value(metadata, "year", "canonical_year"),
        "canonical_release_date": _lookup_value(
            metadata, "release_date", "canonical_release_date"
        ),
        "canonical_bpm": _lookup_value(metadata, "bpm", "canonical_bpm"),
        "canonical_key": _lookup_value(metadata, "key", "canonical_key"),
        "canonical_payload_json": payload_json,
        "duration_ref_ms": _duration_ref_ms(duration_s),
        "ref_source": _lookup_value(
            provenance, "ref_source", "source", "provider", "download_source"
        ),
    }
    return values


def _create_identity_key(fields: Mapping[str, Any], asset_row: sqlite3.Row) -> str:
    isrc = _norm_text(fields.get("isrc"))
    if isrc:
        return f"isrc:{isrc.lower()}"

    for column in PROVIDER_COLUMNS:
        value = _norm_text(fields.get(column))
        if value:
            return f"{column.removesuffix('_id')}:{value}"

    artist_norm = _norm_text(fields.get("artist_norm"))
    title_norm = _norm_text(fields.get("title_norm"))
    if artist_norm and title_norm:
        return f"text:{artist_norm}|{title_norm}"

    asset_id = _row_value(asset_row, "id")
    if asset_id is not None:
        return f"unidentified:asset:{int(asset_id)}"

    asset_path = _norm_text(_row_value(asset_row, "path"))
    if asset_path:
        return f"unidentified:path:{asset_path}"

    raise RuntimeError("unable to construct identity_key")


def _merge_identity_fields_if_empty(
    conn: sqlite3.Connection,
    identity_id: int,
    fields: Mapping[str, Any],
) -> None:
    row = conn.execute("SELECT * FROM track_identity WHERE id = ?", (int(identity_id),)).fetchone()
    if row is None:
        raise LookupError(f"identity not found: {identity_id}")

    updates: dict[str, Any] = {}
    for column, value in fields.items():
        if column == "identity_key" or value is None:
            continue
        if _is_blank_db(_row_value(row, column)):
            updates[column] = value

    if not updates:
        return

    assignments = ", ".join(f"{column} = ?" for column in updates)
    params = [updates[column] for column in updates]
    if _column_exists(conn, "track_identity", "updated_at"):
        assignments = f"{assignments}, updated_at = CURRENT_TIMESTAMP"
    params.append(int(identity_id))

    conn.execute(f"UPDATE track_identity SET {assignments} WHERE id = ?", params)


def _matched_identity_id_by_field(
    conn: sqlite3.Connection,
    column: str,
    value: str,
) -> int | None:
    if not _column_exists(conn, "track_identity", column):
        return None

    has_merged_into = _column_exists(conn, "track_identity", "merged_into_id")
    if has_merged_into:
        row = conn.execute(
            f"""
            SELECT id
            FROM track_identity
            WHERE {column} = ?
            ORDER BY CASE WHEN merged_into_id IS NULL THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """,
            (value,),
        ).fetchone()
    else:
        row = conn.execute(
            f"SELECT id FROM track_identity WHERE {column} = ? ORDER BY id ASC LIMIT 1",
            (value,),
        ).fetchone()

    if row is None:
        return None
    return int(resolve_active_identity(conn, int(row["id"]))["id"])


def _fuzzy_match_identity_id(
    conn: sqlite3.Connection,
    *,
    artist_norm: str | None,
    title_norm: str | None,
    duration_s: float | None,
) -> int | None:
    if not artist_norm or not title_norm:
        return None

    has_merged_into = _column_exists(conn, "track_identity", "merged_into_id")
    where_active = "AND merged_into_id IS NULL" if has_merged_into else ""
    artist_prefix = f"{artist_norm[:4]}%"

    rows = conn.execute(
        f"""
        SELECT
            id,
            artist_norm,
            title_norm,
            canonical_duration,
            duration_ref_ms
        FROM track_identity
        WHERE artist_norm LIKE ?
          AND title_norm IS NOT NULL
          {where_active}
        ORDER BY id ASC
        """,
        (artist_prefix,),
    ).fetchall()

    search_text = f"{artist_norm} {title_norm}"
    best_id: int | None = None
    best_score = 0.0

    for row in rows:
        candidate_duration = _to_float(row["canonical_duration"])
        if candidate_duration is None and row["duration_ref_ms"] is not None:
            candidate_duration = float(int(row["duration_ref_ms"])) / 1000.0

        if duration_s is not None and candidate_duration is not None:
            if abs(duration_s - candidate_duration) > FUZZY_DURATION_TOLERANCE_S:
                continue

        candidate_text = f"{_norm_text(row['artist_norm']) or ''} {_norm_text(row['title_norm']) or ''}"
        score = SequenceMatcher(None, search_text, candidate_text).ratio()
        if score >= FUZZY_SCORE_THRESHOLD and score > best_score:
            best_score = score
            best_id = int(row["id"])

    return best_id


def _create_identity(
    conn: sqlite3.Connection,
    asset_row: sqlite3.Row,
    fields: Mapping[str, Any],
) -> int:
    insert_fields = dict(fields)
    insert_fields["identity_key"] = _create_identity_key(insert_fields, asset_row)
    columns = [column for column, value in insert_fields.items() if value is not None]
    params = [insert_fields[column] for column in columns]
    placeholders = ", ".join("?" for _ in columns)
    conn.execute(
        f"""
        INSERT OR IGNORE INTO track_identity ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        params,
    )
    row = conn.execute(
        "SELECT id FROM track_identity WHERE identity_key = ?",
        (insert_fields["identity_key"],),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to create identity")
    return int(row["id"])


def _identity_duration_ms(identity_row: sqlite3.Row) -> int | None:
    duration_s = _to_float(identity_row["canonical_duration"])
    if duration_s is None:
        return None
    return int(round(duration_s * 1000.0))


def _mirror_file_paths(conn: sqlite3.Connection, identity_id: int, asset_id: int | None) -> list[str]:
    if not _table_exists(conn, "asset_file"):
        return []

    if asset_id is not None:
        rows = conn.execute(
            "SELECT path FROM asset_file WHERE id = ?",
            (int(asset_id),),
        ).fetchall()
        return [str(row["path"]) for row in rows if _norm_text(row["path"])]

    if not _table_exists(conn, "asset_link"):
        return []

    active_where = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    rows = conn.execute(
        f"""
        SELECT af.path AS path
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE al.identity_id = ?
        {active_where}
        ORDER BY af.id ASC
        """,
        (int(identity_id),),
    ).fetchall()
    return [str(row["path"]) for row in rows if _norm_text(row["path"])]


def _mirror_to_files(
    conn: sqlite3.Connection,
    identity_row: sqlite3.Row,
    *,
    asset_id: int | None,
) -> None:
    if not _table_exists(conn, "files"):
        return

    paths = _mirror_file_paths(conn, int(identity_row["id"]), asset_id)
    if not paths:
        return

    file_values: dict[str, Any] = {
        "library_track_key": identity_row["identity_key"],
        "canonical_title": identity_row["canonical_title"],
        "canonical_artist": identity_row["canonical_artist"],
        "canonical_album": identity_row["canonical_album"],
        "canonical_isrc": identity_row["isrc"],
        "canonical_duration": identity_row["canonical_duration"],
        "canonical_duration_source": identity_row["ref_source"],
        "canonical_year": identity_row["canonical_year"],
        "canonical_release_date": identity_row["canonical_release_date"],
        "canonical_bpm": identity_row["canonical_bpm"],
        "canonical_key": identity_row["canonical_key"],
        "canonical_genre": identity_row["canonical_genre"],
        "canonical_sub_genre": identity_row["canonical_sub_genre"],
        "canonical_label": identity_row["canonical_label"],
        "canonical_catalog_number": identity_row["canonical_catalog_number"],
        "canonical_mix_name": identity_row["canonical_mix_name"],
    }
    available = [column for column in file_values if _column_exists(conn, "files", column)]
    if not available:
        logger.warning(
            "mirror_identity_to_legacy: no canonical_* columns found in 'files' "
            "table — mirror skipped for identity %s. Run legacy schema migration first.",
            int(identity_row["id"]),
        )
        return

    assignments = ", ".join(f"{column} = ?" for column in available)
    placeholders = ", ".join("?" for _ in paths)
    params = [file_values[column] for column in available]
    params.extend(paths)
    conn.execute(
        f"""
        UPDATE files
        SET {assignments}
        WHERE path IN ({placeholders})
        """,
        params,
    )


def _mirror_to_library_tracks(conn: sqlite3.Connection, identity_row: sqlite3.Row) -> None:
    if not _table_exists(conn, "library_tracks"):
        return

    conn.execute(
        """
        INSERT INTO library_tracks (
            library_track_key,
            title,
            artist,
            album,
            duration_ms,
            isrc,
            release_date,
            genre,
            bpm,
            musical_key,
            label,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(library_track_key) DO UPDATE SET
            title = excluded.title,
            artist = excluded.artist,
            album = excluded.album,
            duration_ms = excluded.duration_ms,
            isrc = excluded.isrc,
            release_date = excluded.release_date,
            genre = excluded.genre,
            bpm = excluded.bpm,
            musical_key = excluded.musical_key,
            label = excluded.label,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            identity_row["identity_key"],
            identity_row["canonical_title"],
            identity_row["canonical_artist"],
            identity_row["canonical_album"],
            _identity_duration_ms(identity_row),
            identity_row["isrc"],
            identity_row["canonical_release_date"],
            identity_row["canonical_genre"],
            identity_row["canonical_bpm"],
            identity_row["canonical_key"],
            identity_row["canonical_label"],
        ),
    )


def resolve_active_identity(conn: sqlite3.Connection, identity_id: int) -> sqlite3.Row:
    """Resolve an identity row to the active canonical row.

    The function follows ``merged_into_id`` until it reaches a row whose
    ``merged_into_id`` is null, then returns that row.
    """
    if not _table_exists(conn, "track_identity"):
        raise RuntimeError("track_identity table is missing")

    has_merged_into = _column_exists(conn, "track_identity", "merged_into_id")
    current_id = int(identity_id)
    seen_ids: set[int] = set()

    while True:
        row = conn.execute(
            "SELECT * FROM track_identity WHERE id = ?",
            (current_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"identity not found: {current_id}")
        if not has_merged_into:
            return row

        if current_id in seen_ids:
            raise RuntimeError(f"merged_into_id cycle detected at identity {current_id}")
        seen_ids.add(current_id)

        merged_into_raw = row["merged_into_id"]
        if merged_into_raw is None:
            return row
        current_id = int(merged_into_raw)


def resolve_or_create_identity(
    conn: sqlite3.Connection,
    asset_row: sqlite3.Row,
    metadata: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> int:
    """Resolve an asset to an existing identity or create a new one.

    Resolution order:
    1. existing active asset link
    2. ISRC
    3. provider IDs
    4. fuzzy artist/title/duration
    5. create new identity
    """
    if not _table_exists(conn, "track_identity"):
        raise RuntimeError("track_identity table is missing")

    owns_transaction = not conn.in_transaction
    if owns_transaction:
        conn.execute("BEGIN IMMEDIATE")

    try:
        fields = _identity_value_map(asset_row, metadata, provenance)
        asset_id_raw = _row_value(asset_row, "id")
        asset_id = int(asset_id_raw) if asset_id_raw is not None else None

        if asset_id is not None and _table_exists(conn, "asset_link"):
            active_link_where = "AND active = 1" if _column_exists(conn, "asset_link", "active") else ""
            linked = conn.execute(
                f"""
                SELECT identity_id
                FROM asset_link
                WHERE asset_id = ?
                {active_link_where}
                ORDER BY id ASC
                LIMIT 1
                """,
                (asset_id,),
            ).fetchone()
            if linked is not None:
                resolved = resolve_active_identity(conn, int(linked["identity_id"]))
                resolved_id = int(resolved["id"])
                _merge_identity_fields_if_empty(conn, resolved_id, fields)
                if owns_transaction:
                    conn.commit()
                return resolved_id

        isrc = _norm_text(fields.get("isrc"))
        if isrc:
            matched_id = _matched_identity_id_by_field(conn, "isrc", isrc)
            if matched_id is not None:
                _merge_identity_fields_if_empty(conn, matched_id, fields)
                if owns_transaction:
                    conn.commit()
                return matched_id

        for column in PROVIDER_COLUMNS:
            value = _norm_text(fields.get(column))
            if not value:
                continue
            matched_id = _matched_identity_id_by_field(conn, column, value)
            if matched_id is not None:
                _merge_identity_fields_if_empty(conn, matched_id, fields)
                if owns_transaction:
                    conn.commit()
                return matched_id

        matched_id = _fuzzy_match_identity_id(
            conn,
            artist_norm=_norm_text(fields.get("artist_norm")),
            title_norm=_norm_text(fields.get("title_norm")),
            duration_s=_to_float(fields.get("canonical_duration")),
        )
        if matched_id is not None:
            _merge_identity_fields_if_empty(conn, matched_id, fields)
            if owns_transaction:
                conn.commit()
            return matched_id

        created_id = _create_identity(conn, asset_row, fields)
        if owns_transaction:
            conn.commit()
        return created_id
    except Exception:
        if owns_transaction:
            conn.rollback()
        raise


def link_asset_to_identity(
    conn: sqlite3.Connection,
    asset_id: int,
    identity_id: int,
    confidence: float,
    link_source: str,
) -> None:
    """Create or update the canonical asset-to-identity link for an asset."""
    conn.execute(
        """
        INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(asset_id) DO UPDATE SET
            identity_id = excluded.identity_id,
            confidence = excluded.confidence,
            link_source = excluded.link_source,
            active = 1,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(asset_id), int(identity_id), float(confidence), link_source),
    )


def mirror_identity_to_legacy(
    conn: sqlite3.Connection,
    identity_id: int,
    asset_id: int | None,
) -> None:
    """Mirror canonical identity state into legacy compatibility tables."""
    identity_row = resolve_active_identity(conn, int(identity_id))
    _mirror_to_files(conn, identity_row, asset_id=asset_id)
    _mirror_to_library_tracks(conn, identity_row)
