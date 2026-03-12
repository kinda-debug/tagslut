"""Backfill v3 asset/identity/link rows from legacy file inventory."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from tagslut.storage.schema import (
    V3_ASSET_FILE_TABLE,
    V3_ASSET_LINK_TABLE,
    V3_TRACK_IDENTITY_TABLE,
    init_db,
)
from tagslut.storage.v3.dual_write import upsert_asset_file
from tagslut.utils import env_paths

_PROVIDER_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("beatport_id", ("beatport_id", "beatport_track_id", "bp_track_id")),
    ("tidal_id", ("tidal_id", "tidal_track_id")),
    ("qobuz_id", ("qobuz_id", "qobuz_track_id")),
    ("spotify_id", ("spotify_id", "spotify_track_id")),
    ("apple_music_id", ("apple_music_id", "apple_track_id")),
    ("deezer_id", ("deezer_id", "deezer_track_id")),
    ("traxsource_id", ("traxsource_id", "traxsource_track_id")),
    ("itunes_id", ("itunes_id", "itunes_track_id")),
    ("musicbrainz_id", ("musicbrainz_id", "musicbrainz_track_id")),
)
_FUZZY_DURATION_TOLERANCE_MS = 2_000
_SAMPLE_LIMIT = 10
_SAMPLE_CATEGORIES = (
    "created",
    "reused",
    "merged",
    "skipped",
    "conflicted",
    "fuzzy_near_collision",
    "fingerprint_matched",
    "errors",
)


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
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return " ".join(text.lower().split())


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _duration_ms_from_mapping(data: dict[str, Any] | None) -> int | None:
    if not data:
        return None
    for key in ("duration_ref_ms", "duration_measured_ms", "duration_ms"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            continue
    for key in ("duration_s", "duration", "canonical_duration"):
        value = data.get(key)
        if value is None:
            continue
        try:
            return int(round(float(str(value)) * 1000))
        except (TypeError, ValueError):
            continue
    return None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _load_file_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(files)").fetchall()}


def _load_track_identity_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({V3_TRACK_IDENTITY_TABLE})").fetchall()}


def _load_library_tracks(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    if not _column_exists(conn, "library_tracks", "library_track_key"):
        return {}
    rows = conn.execute("SELECT * FROM library_tracks").fetchall()
    return {str(row["library_track_key"]): row for row in rows if row["library_track_key"]}


def _load_library_track_sources(
    conn: sqlite3.Connection,
) -> dict[str, list[dict[str, Any]]]:
    if not _column_exists(conn, "library_track_sources", "library_track_key"):
        return {}
    rows = conn.execute(
        """
        SELECT library_track_key, service, service_track_id, url, metadata_json, isrc,
               match_confidence, fetched_at
        FROM library_track_sources
        ORDER BY id ASC
        """
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = _norm_text(row["library_track_key"])
        if not key:
            continue
        grouped[key].append(
            {
                "service": _norm_text(row["service"]),
                "service_track_id": _norm_text(row["service_track_id"]),
                "url": _norm_text(row["url"]),
                "metadata_json": _parse_json(row["metadata_json"]),
                "isrc": _norm_text(row["isrc"]),
                "match_confidence": _norm_text(row["match_confidence"]),
                "fetched_at": _norm_text(row["fetched_at"]),
            }
        )
    return grouped


def _append_sample(samples: dict[str, list[dict[str, Any]]], key: str, row: dict[str, Any]) -> None:
    bucket = samples.setdefault(key, [])
    if len(bucket) < _SAMPLE_LIMIT:
        bucket.append(row)


@dataclass
class BackfillStats:
    processed: int = 0
    created: int = 0
    reused: int = 0
    merged: int = 0
    skipped: int = 0
    conflicted: int = 0
    fuzzy_near_collision: int = 0
    errors: int = 0
    fingerprint_matched: int = 0
    committed_batches: int = 0
    last_file_id: int = 0
    samples: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {key: [] for key in _SAMPLE_CATEGORIES}
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "created": self.created,
            "reused": self.reused,
            "merged": self.merged,
            "skipped": self.skipped,
            "conflicted": self.conflicted,
            "fuzzy_near_collision": self.fuzzy_near_collision,
            "errors": self.errors,
            "fingerprint_matched": self.fingerprint_matched,
            "committed_batches": self.committed_batches,
            "last_file_id": self.last_file_id,
            "samples": self.samples,
        }


@dataclass(frozen=True)
class BackfillConfig:
    execute: bool
    resume_from_file_id: int
    commit_every: int
    checkpoint_every: int
    busy_timeout_ms: int
    abort_error_rate_per_1000: float
    artifacts_dir: Path
    limit: int | None = None
    verbose: bool = False


def _maybe_set(payload: dict[str, Any], key: str, value: Any) -> None:
    if key not in payload or payload[key] in (None, ""):
        normalized = _norm_text(value)
        if normalized:
            payload[key] = normalized


def _maybe_set_float(payload: dict[str, Any], key: str, value: Any) -> None:
    if key in payload and payload[key] not in (None, ""):
        return
    if value in (None, ""):
        return
    try:
        payload[key] = float(str(value))
    except (TypeError, ValueError):
        return


def _maybe_set_int(payload: dict[str, Any], key: str, value: Any) -> None:
    if key in payload and payload[key] not in (None, ""):
        return
    if value in (None, ""):
        return
    try:
        payload[key] = int(float(str(value)))
    except (TypeError, ValueError):
        return


def _extract_identity_payload(
    file_row: sqlite3.Row,
    library_track: sqlite3.Row | None,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    file_metadata = _parse_json(file_row["metadata_json"]) if "metadata_json" in file_row.keys() else {}

    if library_track is not None:
        _maybe_set(payload, "canonical_title", library_track["title"])
        _maybe_set(payload, "canonical_artist", library_track["artist"])
        _maybe_set(payload, "canonical_album", library_track["album"])
        _maybe_set(payload, "isrc", library_track["isrc"])
        _maybe_set(payload, "canonical_release_date", library_track["release_date"])
        _maybe_set(payload, "canonical_genre", library_track["genre"])
        _maybe_set(payload, "canonical_key", library_track["musical_key"])
        _maybe_set(payload, "canonical_label", library_track["label"])
        _maybe_set_float(payload, "canonical_bpm", library_track["bpm"])
        _maybe_set_int(payload, "duration_ref_ms", library_track["duration_ms"])
        _maybe_set(payload, "ref_source", "library_tracks")

    for key in (
        "canonical_title",
        "canonical_artist",
        "canonical_album",
        "canonical_genre",
        "canonical_sub_genre",
        "canonical_label",
        "canonical_catalog_number",
        "canonical_mix_name",
        "canonical_release_date",
        "canonical_isrc",
        "isrc",
        "beatport_id",
        "tidal_id",
        "qobuz_id",
        "spotify_id",
        "apple_music_id",
        "deezer_id",
        "traxsource_id",
        "itunes_id",
        "musicbrainz_id",
    ):
        if key not in file_row.keys():
            continue
        if key == "canonical_isrc":
            _maybe_set(payload, "isrc", file_row[key])
        else:
            _maybe_set(payload, key, file_row[key])
    if "canonical_bpm" in file_row.keys():
        _maybe_set_float(payload, "canonical_bpm", file_row["canonical_bpm"])
    if "canonical_year" in file_row.keys():
        _maybe_set_int(payload, "canonical_year", file_row["canonical_year"])
    if "duration_ref_ms" in file_row.keys():
        _maybe_set_int(payload, "duration_ref_ms", file_row["duration_ref_ms"])
    if "duration_measured_ms" in file_row.keys():
        _maybe_set_int(payload, "duration_ref_ms", file_row["duration_measured_ms"])
    if "duration" in file_row.keys():
        duration_value = file_row["duration"]
        duration_ms = None
        if duration_value is not None:
            duration_ms = int(round(float(duration_value) * 1000))
        _maybe_set_int(payload, "duration_ref_ms", duration_ms)
    if "duration_ref_source" in file_row.keys():
        _maybe_set(payload, "ref_source", file_row["duration_ref_source"])

    for source in sources:
        service = _norm_text(source.get("service"))
        service_track_id = _norm_text(source.get("service_track_id"))
        if service and service_track_id:
            for provider_column, aliases in _PROVIDER_COLUMNS:
                if service.lower() in aliases or service.lower() == provider_column.removesuffix("_id"):
                    _maybe_set(payload, provider_column, service_track_id)
                    break
        _maybe_set(payload, "isrc", source.get("isrc"))
        metadata = source.get("metadata_json") or {}
        if isinstance(metadata, dict):
            for provider_column, aliases in _PROVIDER_COLUMNS:
                for alias in aliases:
                    _maybe_set(payload, provider_column, metadata.get(alias))
            _maybe_set(
                payload, "canonical_title", metadata.get("canonical_title") or metadata.get("title")
            )
            _maybe_set(
                payload, "canonical_artist", metadata.get("canonical_artist") or metadata.get("artist")
            )
            _maybe_set(
                payload, "canonical_album", metadata.get("canonical_album") or metadata.get("album")
            )
            _maybe_set(
                payload, "canonical_genre", metadata.get("canonical_genre") or metadata.get("genre")
            )
            _maybe_set(
                payload, "canonical_label", metadata.get("canonical_label") or metadata.get("label")
            )
            _maybe_set(payload, "canonical_key", metadata.get("canonical_key") or metadata.get("key"))
            _maybe_set(
                payload,
                "canonical_release_date",
                metadata.get("canonical_release_date") or metadata.get("date"),
            )
            _maybe_set_float(
                payload, "canonical_bpm", metadata.get("canonical_bpm") or metadata.get("bpm")
            )
            _maybe_set_int(payload, "duration_ref_ms", _duration_ms_from_mapping(metadata))
            _maybe_set(payload, "ref_source", service or source.get("url"))

    for provider_column, aliases in _PROVIDER_COLUMNS:
        for alias in aliases:
            _maybe_set(payload, provider_column, file_metadata.get(alias))
    _maybe_set(payload, "isrc", file_metadata.get("isrc") or file_metadata.get("tsrc"))
    _maybe_set(
        payload, "canonical_title", file_metadata.get("canonical_title") or file_metadata.get("title")
    )
    _maybe_set(
        payload,
        "canonical_artist",
        file_metadata.get("canonical_artist")
        or file_metadata.get("artist")
        or file_metadata.get("albumartist"),
    )
    _maybe_set(payload, "canonical_album", file_metadata.get("canonical_album") or file_metadata.get("album"))
    _maybe_set(payload, "canonical_genre", file_metadata.get("canonical_genre") or file_metadata.get("genre"))
    _maybe_set(
        payload,
        "canonical_sub_genre",
        file_metadata.get("canonical_sub_genre") or file_metadata.get("sub_genre"),
    )
    _maybe_set(payload, "canonical_label", file_metadata.get("canonical_label") or file_metadata.get("label"))
    _maybe_set(
        payload,
        "canonical_catalog_number",
        file_metadata.get("canonical_catalog_number") or file_metadata.get("catalog_number"),
    )
    _maybe_set(payload, "canonical_mix_name", file_metadata.get("canonical_mix_name") or file_metadata.get("mix_name"))
    _maybe_set(
        payload,
        "canonical_release_date",
        file_metadata.get("canonical_release_date") or file_metadata.get("date"),
    )
    _maybe_set(
        payload,
        "canonical_key",
        file_metadata.get("canonical_key") or file_metadata.get("key") or file_metadata.get("initialkey"),
    )
    _maybe_set_float(payload, "canonical_bpm", file_metadata.get("canonical_bpm") or file_metadata.get("bpm"))
    _maybe_set_int(payload, "canonical_year", file_metadata.get("canonical_year") or file_metadata.get("year"))
    _maybe_set_int(payload, "duration_ref_ms", _duration_ms_from_mapping(file_metadata))
    _maybe_set(payload, "ref_source", payload.get("ref_source") or "metadata_json")

    payload["artist_norm"] = _norm_name(payload.get("canonical_artist"))
    payload["title_norm"] = _norm_name(payload.get("canonical_title"))
    payload["album_norm"] = _norm_name(payload.get("canonical_album"))
    return payload


def _extract_asset_payload(file_row: sqlite3.Row) -> dict[str, Any]:
    return {
        "path": file_row["path"],
        "content_sha256": file_row["sha256"] if "sha256" in file_row.keys() else None,
        "streaminfo_md5": file_row["streaminfo_md5"] if "streaminfo_md5" in file_row.keys() else None,
        "checksum": file_row["checksum"] if "checksum" in file_row.keys() else None,
        "size_bytes": file_row["size"] if "size" in file_row.keys() else None,
        "mtime": file_row["mtime"] if "mtime" in file_row.keys() else None,
        "duration_s": file_row["duration"] if "duration" in file_row.keys() else None,
        "sample_rate": file_row["sample_rate"] if "sample_rate" in file_row.keys() else None,
        "bit_depth": file_row["bit_depth"] if "bit_depth" in file_row.keys() else None,
        "bitrate": file_row["bitrate"] if "bitrate" in file_row.keys() else None,
        "library": file_row["library"] if "library" in file_row.keys() else None,
        "zone": file_row["zone"] if "zone" in file_row.keys() else None,
        "download_source": file_row["download_source"] if "download_source" in file_row.keys() else None,
        "download_date": file_row["download_date"] if "download_date" in file_row.keys() else None,
        "mgmt_status": file_row["mgmt_status"] if "mgmt_status" in file_row.keys() else None,
    }


def _identity_key_for_payload(payload: dict[str, Any]) -> str | None:
    isrc = _norm_text(payload.get("isrc"))
    if isrc:
        return f"isrc:{isrc.lower()}"
    for provider_column, _ in _PROVIDER_COLUMNS:
        value = _norm_text(payload.get(provider_column))
        if value:
            return f"{provider_column}:{value}"
    if payload.get("artist_norm") and payload.get("title_norm"):
        return f"text:{payload['artist_norm']}|{payload['title_norm']}"
    return None


def _resolve_active_identity_row(
    conn: sqlite3.Connection, identity_row: sqlite3.Row
) -> tuple[sqlite3.Row, bool]:
    merged_into_id = identity_row["merged_into_id"] if "merged_into_id" in identity_row.keys() else None
    if merged_into_id is None:
        return identity_row, False
    canonical = conn.execute(
        f"SELECT * FROM {V3_TRACK_IDENTITY_TABLE} WHERE id = ?",
        (merged_into_id,),
    ).fetchone()
    if canonical is None:
        raise RuntimeError(f"merged identity target missing: {merged_into_id}")
    return canonical, True


def _identity_row_score(row: sqlite3.Row) -> tuple[int, int]:
    score = 0
    for field_name in (
        "isrc",
        *(name for name, _ in _PROVIDER_COLUMNS),
        "artist_norm",
        "title_norm",
        "album_norm",
        "canonical_artist",
        "canonical_title",
        "canonical_album",
        "canonical_genre",
        "canonical_label",
        "canonical_release_date",
        "duration_ref_ms",
        "ref_source",
    ):
        if field_name in row.keys() and _norm_text(row[field_name]) is not None:
            score += 1
    return (score, -int(row["id"]))


def _rows_have_consistent_exact_fields(rows: list[sqlite3.Row]) -> bool:
    for field_name in ("isrc", *(name for name, _ in _PROVIDER_COLUMNS)):
        values = set()
        for row in rows:
            if field_name not in row.keys():
                continue
            value = _norm_text(row[field_name])
            if value:
                values.add(value.lower())
        if len(values) > 1:
            return False
    return True


def _rows_have_compatible_core_identity(rows: list[sqlite3.Row]) -> bool:
    artist_values = {_norm_text(row["artist_norm"]) for row in rows if "artist_norm" in row.keys()}
    artist_values.discard(None)
    title_values = {_norm_text(row["title_norm"]) for row in rows if "title_norm" in row.keys()}
    title_values.discard(None)
    if len(artist_values) > 1 or len(title_values) > 1:
        return False
    durations = []
    for row in rows:
        if "duration_ref_ms" not in row.keys():
            continue
        value = row["duration_ref_ms"]
        if value is None:
            continue
        durations.append(int(value))
    if durations and max(durations) - min(durations) > _FUZZY_DURATION_TOLERANCE_MS:
        return False
    return True


def _choose_equivalent_identity(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    if not rows or not _rows_have_compatible_core_identity(rows):
        return None
    if not _rows_have_consistent_exact_fields(rows):
        return None
    return max(rows, key=_identity_row_score)


def _find_identity_by_asset_path(conn: sqlite3.Connection, path: str) -> tuple[int | None, bool]:
    if not _table_exists(conn, V3_ASSET_FILE_TABLE) or not _table_exists(conn, V3_ASSET_LINK_TABLE):
        return None, False
    row = conn.execute(
        f"""
        SELECT ti.*
        FROM {V3_ASSET_FILE_TABLE} af
        JOIN {V3_ASSET_LINK_TABLE} al ON al.asset_id = af.id
        JOIN {V3_TRACK_IDENTITY_TABLE} ti ON ti.id = al.identity_id
        WHERE af.path = ? AND al.active = 1
        LIMIT 1
        """,
        (path,),
    ).fetchone()
    if row is None:
        return None, False
    canonical, followed = _resolve_active_identity_row(conn, row)
    return int(canonical["id"]), followed


def _find_identity_by_exact_field(
    conn: sqlite3.Connection, field: str, value: str | None
) -> tuple[int | None, bool, bool]:
    if not _table_exists(conn, V3_TRACK_IDENTITY_TABLE):
        return None, False, False
    if not _column_exists(conn, V3_TRACK_IDENTITY_TABLE, field):
        return None, False, False
    if not value:
        return None, False, False
    rows = conn.execute(
        f"SELECT * FROM {V3_TRACK_IDENTITY_TABLE} WHERE {field} = ? ORDER BY id ASC",
        (value,),
    ).fetchall()
    if not rows:
        return None, False, False
    canonical_rows: dict[int, sqlite3.Row] = {}
    followed_merge = False
    for row in rows:
        canonical, followed = _resolve_active_identity_row(conn, row)
        canonical_rows[int(canonical["id"])] = canonical
        followed_merge = followed_merge or followed
    if len(canonical_rows) > 1:
        equivalent = _choose_equivalent_identity(list(canonical_rows.values()))
        if equivalent is not None:
            return int(equivalent["id"]), followed_merge, False
        return None, followed_merge, True
    return min(canonical_rows), followed_merge, False


def _find_identity_by_identity_key(conn: sqlite3.Connection, identity_key: str | None) -> tuple[int | None, bool]:
    if not _table_exists(conn, V3_TRACK_IDENTITY_TABLE):
        return None, False
    if not identity_key:
        return None, False
    row = conn.execute(
        f"SELECT * FROM {V3_TRACK_IDENTITY_TABLE} WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    if row is None:
        return None, False
    canonical, followed = _resolve_active_identity_row(conn, row)
    return int(canonical["id"]), followed


def _find_fuzzy_candidates(conn: sqlite3.Connection, payload: dict[str, Any]) -> list[int]:
    if not _table_exists(conn, V3_TRACK_IDENTITY_TABLE):
        return []
    if not _column_exists(conn, V3_TRACK_IDENTITY_TABLE, "artist_norm") or not _column_exists(
        conn, V3_TRACK_IDENTITY_TABLE, "title_norm"
    ):
        return []
    artist_norm = _norm_text(payload.get("artist_norm"))
    title_norm = _norm_text(payload.get("title_norm"))
    if not artist_norm or not title_norm:
        return []
    params: list[Any] = [artist_norm, title_norm]
    duration_sql = ""
    duration_ref_ms = payload.get("duration_ref_ms")
    if duration_ref_ms is not None:
        duration_sql = " AND duration_ref_ms IS NOT NULL AND ABS(duration_ref_ms - ?) <= ?"
        params.extend([int(duration_ref_ms), _FUZZY_DURATION_TOLERANCE_MS])
    merged_predicate = ""
    if _column_exists(conn, V3_TRACK_IDENTITY_TABLE, "merged_into_id"):
        merged_predicate = "AND merged_into_id IS NULL"
    rows = conn.execute(
        f"""
        SELECT id
        FROM {V3_TRACK_IDENTITY_TABLE}
        WHERE artist_norm = ?
          AND title_norm = ?
          {merged_predicate}
          {duration_sql}
        ORDER BY id ASC
        """,
        tuple(params),
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _resolve_equivalent_fuzzy_candidates(
    conn: sqlite3.Connection, candidate_ids: list[int]
) -> int | None:
    if len(candidate_ids) <= 1:
        return candidate_ids[0] if candidate_ids else None
    rows = conn.execute(
        f"""
        SELECT *
        FROM {V3_TRACK_IDENTITY_TABLE}
        WHERE id IN ({", ".join("?" for _ in candidate_ids)})
        ORDER BY id ASC
        """,
        tuple(candidate_ids),
    ).fetchall()
    equivalent = _choose_equivalent_identity(list(rows))
    if equivalent is None:
        return None
    return int(equivalent["id"])


def _update_identity(conn: sqlite3.Connection, identity_id: int, payload: dict[str, Any], *, fuzzy: bool) -> None:
    current = conn.execute(
        f"SELECT * FROM {V3_TRACK_IDENTITY_TABLE} WHERE id = ?",
        (identity_id,),
    ).fetchone()
    if current is None:
        raise LookupError(f"identity not found: {identity_id}")
    available_columns = _load_track_identity_columns(conn)
    updates: dict[str, Any] = {}
    exact_fields = {"isrc", *(name for name, _ in _PROVIDER_COLUMNS)}
    for field_name, value in payload.items():
        if field_name not in available_columns:
            continue
        if value is None:
            continue
        current_value = current[field_name] if field_name in current.keys() else None
        if fuzzy and field_name in exact_fields and _norm_text(current_value):
            continue
        if current_value is None or str(current_value).strip() == "":
            updates[field_name] = value
    if not updates:
        return
    assignments = ", ".join(f"{field} = ?" for field in updates)
    params = [updates[field] for field in updates]
    params.append(identity_id)
    conn.execute(
        f"UPDATE {V3_TRACK_IDENTITY_TABLE} SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        tuple(params),
    )


def _insert_identity(conn: sqlite3.Connection, payload: dict[str, Any]) -> int:
    identity_key = _identity_key_for_payload(payload)
    if not identity_key:
        raise RuntimeError("cannot create identity without exact or fuzzy identity fields")
    existing_id, _ = _find_identity_by_identity_key(conn, identity_key)
    if existing_id is not None:
        return existing_id
    full_payload = dict(payload)
    full_payload["identity_key"] = identity_key
    available_columns = _load_track_identity_columns(conn)
    columns = [
        key for key, value in full_payload.items() if value is not None and key in available_columns
    ]
    placeholders = ", ".join("?" for _ in columns)
    try:
        conn.execute(
            f"INSERT INTO {V3_TRACK_IDENTITY_TABLE} ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(full_payload[column] for column in columns),
        )
    except sqlite3.IntegrityError as exc:
        existing_id, _ = _find_identity_by_identity_key(conn, identity_key)
        if existing_id is not None:
            return existing_id
        raise exc
    row = conn.execute(
        f"SELECT id FROM {V3_TRACK_IDENTITY_TABLE} WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to create track identity")
    return int(row["id"])


def _link_asset(conn: sqlite3.Connection, asset_id: int, identity_id: int, confidence: float, link_source: str) -> None:
    conn.execute(
        f"UPDATE {V3_ASSET_LINK_TABLE} SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE asset_id = ?",
        (asset_id,),
    )
    existing = conn.execute(
        f"SELECT id FROM {V3_ASSET_LINK_TABLE} WHERE asset_id = ? AND identity_id = ?",
        (asset_id, identity_id),
    ).fetchone()
    if existing is None:
        conn.execute(
            f"""
            INSERT INTO {V3_ASSET_LINK_TABLE} (asset_id, identity_id, confidence, link_source, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (asset_id, identity_id, confidence, link_source),
        )
        return
    conn.execute(
        f"""
        UPDATE {V3_ASSET_LINK_TABLE}
        SET confidence = ?, link_source = ?, active = 1, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (confidence, link_source, int(existing["id"])),
    )



def _seed_legacy_fingerprint(conn, asset_id, file_row, file_columns):
    """Copy legacy files.fingerprint to asset_file.chromaprint_fingerprint if not yet set."""
    if "fingerprint" not in file_columns:
        return
    fp = _norm_text(file_row["fingerprint"])
    if not fp:
        return
    if not _column_exists(conn, V3_ASSET_FILE_TABLE, "chromaprint_fingerprint"):
        return
    conn.execute(
        f"UPDATE {V3_ASSET_FILE_TABLE} SET chromaprint_fingerprint = ? WHERE id = ? AND chromaprint_fingerprint IS NULL",
        (fp, asset_id),
    )


def _find_identity_by_legacy_fingerprint(conn, file_row, file_columns, asset_id):
    """Tier-4 identity lookup via legacy files.fingerprint -> asset_file.chromaprint_fingerprint."""
    if "fingerprint" not in file_columns:
        return None
    fp = _norm_text(file_row["fingerprint"])
    if not fp:
        return None
    if not _column_exists(conn, V3_ASSET_FILE_TABLE, "chromaprint_fingerprint"):
        return None
    from tagslut.storage.v3.chromaprint import find_identity_by_fingerprint
    return find_identity_by_fingerprint(conn, fp, exclude_asset_id=asset_id)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _checkpoint_payload(stats: BackfillStats, *, mode: str, db_path: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "db_path": db_path,
        **stats.as_dict(),
    }


def _emit_progress(config: BackfillConfig, stats: BackfillStats, *, event: str) -> None:
    if not config.verbose:
        return
    print(
        "progress "
        f"event={event} processed={stats.processed} last_file_id={stats.last_file_id} "
        f"created={stats.created} reused={stats.reused} merged={stats.merged} "
        f"skipped={stats.skipped} conflicted={stats.conflicted} errors={stats.errors} "
        f"fingerprint_matched={stats.fingerprint_matched} committed_batches={stats.committed_batches}",
        file=sys.stderr,
        flush=True,
    )


def backfill_v3_identity_links(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    config: BackfillConfig,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {config.busy_timeout_ms}")
    if config.execute:
        init_db(conn)

    file_columns = _load_file_columns(conn)
    library_tracks = _load_library_tracks(conn)
    library_track_sources = _load_library_track_sources(conn)
    artifacts_dir = config.artifacts_dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    stats = BackfillStats()
    mode = "execute" if config.execute else "dry_run"

    select_columns = [
        "rowid AS file_id",
        "*",
    ]
    query = f"SELECT {', '.join(select_columns)} FROM files WHERE rowid > ? ORDER BY rowid ASC"
    params: list[Any] = [config.resume_from_file_id]
    if config.limit is not None:
        query += " LIMIT ?"
        params.append(config.limit)
    rows = conn.execute(query, tuple(params)).fetchall()

    if config.execute:
        conn.execute("BEGIN")

    for row in rows:
        file_id = int(row["file_id"])
        stats.last_file_id = file_id
        try:
            library_track_key = _norm_text(row["library_track_key"]) if "library_track_key" in file_columns else None
            payload = _extract_identity_payload(
                row,
                library_tracks.get(library_track_key) if library_track_key else None,
                library_track_sources.get(library_track_key, []) if library_track_key else [],
            )
            identity_key = _identity_key_for_payload(payload)
            if not identity_key:
                stats.skipped += 1
                _append_sample(
                    stats.samples,
                    "skipped",
                    {"file_id": file_id, "path": row["path"], "reason": "no_identity_hints"},
                )
                stats.processed += 1
                continue

            asset_payload = _extract_asset_payload(row)
            asset_id: int | None = None
            if config.execute:
                asset_id = upsert_asset_file(conn, **asset_payload)
                _seed_legacy_fingerprint(conn, asset_id, row, file_columns)

            resolved_identity_id: int | None = None
            merged = False
            conflicted = False

            asset_match_id, asset_followed_merge = _find_identity_by_asset_path(conn, str(row["path"]))
            if asset_match_id is not None:
                resolved_identity_id = asset_match_id
                merged = asset_followed_merge
            else:
                exact_fields = [("isrc", _norm_text(payload.get("isrc")))]
                exact_fields.extend(
                    (provider, _norm_text(payload.get(provider)))
                    for provider, _ in _PROVIDER_COLUMNS
                )
                for field_name, value in exact_fields:
                    match_id, followed_merge, exact_conflict = _find_identity_by_exact_field(
                        conn, field_name, value
                    )
                    if exact_conflict:
                        conflicted = True
                        _append_sample(
                            stats.samples,
                            "conflicted",
                            {
                                "file_id": file_id,
                                "path": row["path"],
                                "field": field_name,
                                "value": value,
                            },
                        )
                        break
                    if match_id is not None:
                        resolved_identity_id = match_id
                        merged = merged or followed_merge
                        break

            if conflicted:
                stats.conflicted += 1
                stats.processed += 1
                continue

            identity_key_match_id, identity_key_followed_merge = _find_identity_by_identity_key(
                conn, identity_key
            )
            if resolved_identity_id is None and identity_key_match_id is not None:
                resolved_identity_id = identity_key_match_id
                merged = merged or identity_key_followed_merge

            fuzzy_candidates = _find_fuzzy_candidates(conn, payload)
            equivalent_fuzzy_identity_id = _resolve_equivalent_fuzzy_candidates(conn, fuzzy_candidates)
            if resolved_identity_id is None and equivalent_fuzzy_identity_id is not None:
                resolved_identity_id = equivalent_fuzzy_identity_id
                fuzzy_candidates = [equivalent_fuzzy_identity_id]
            if resolved_identity_id is None and len(fuzzy_candidates) > 1:
                stats.fuzzy_near_collision += 1
                stats.conflicted += 1
                _append_sample(
                    stats.samples,
                    "fuzzy_near_collision",
                    {
                        "file_id": file_id,
                        "path": row["path"],
                        "candidate_identity_ids": fuzzy_candidates,
                    },
                )
                stats.processed += 1
                continue
            if resolved_identity_id is None and len(fuzzy_candidates) == 1:
                resolved_identity_id = fuzzy_candidates[0]

            if resolved_identity_id is None:
                resolved_identity_id = _find_identity_by_legacy_fingerprint(
                    conn, row, file_columns, asset_id
                )
                if resolved_identity_id is not None:
                    stats.fingerprint_matched += 1
                    _append_sample(
                        stats.samples,
                        "fingerprint_matched",
                        {"file_id": file_id, "path": row["path"], "identity_id": resolved_identity_id},
                    )

            if resolved_identity_id is None:
                if config.execute:
                    resolved_identity_id = _insert_identity(conn, payload)
                stats.created += 1
                _append_sample(
                    stats.samples,
                    "created",
                    {"file_id": file_id, "path": row["path"], "identity_key": identity_key},
                )
            else:
                if config.execute:
                    _update_identity(conn, resolved_identity_id, payload, fuzzy=len(fuzzy_candidates) == 1)
                stats.reused += 1
                _append_sample(
                    stats.samples,
                    "reused",
                    {"file_id": file_id, "path": row["path"], "identity_id": resolved_identity_id},
                )
            if merged:
                stats.merged += 1
                _append_sample(
                    stats.samples,
                    "merged",
                    {"file_id": file_id, "path": row["path"], "identity_id": resolved_identity_id},
                )

            if config.execute and asset_id is not None and resolved_identity_id is not None:
                confidence = 1.0 if _norm_text(payload.get("isrc")) else 0.9 if any(
                    _norm_text(payload.get(provider)) for provider, _ in _PROVIDER_COLUMNS
                ) else 0.7
                _link_asset(conn, asset_id, resolved_identity_id, confidence, "backfill_v3")
            stats.processed += 1
        except Exception as exc:  # pragma: no cover - exercised via abort threshold tests
            stats.errors += 1
            _append_sample(
                stats.samples,
                "errors",
                {"file_id": file_id, "path": row["path"], "error": str(exc)},
            )
            stats.processed += 1
            error_rate = (stats.errors * 1000.0) / max(stats.processed, 1)
            if error_rate > config.abort_error_rate_per_1000:
                abort_path = artifacts_dir / f"backfill_v3_abort_{stamp}.json"
                _write_json(abort_path, _checkpoint_payload(stats, mode=mode, db_path=str(db_path)))
                if config.execute:
                    conn.rollback()
                raise RuntimeError(
                    "Backfill aborted: error rate "
                    f"{error_rate:.2f}/1000 exceeds threshold "
                    f"{config.abort_error_rate_per_1000:.2f}/1000"
                ) from exc

        if config.execute and stats.processed % config.commit_every == 0:
            conn.commit()
            stats.committed_batches += 1
            _emit_progress(config, stats, event="commit")
            conn.execute("BEGIN")
        if stats.processed % config.checkpoint_every == 0:
            checkpoint_path = artifacts_dir / f"backfill_v3_checkpoint_{stamp}_{stats.last_file_id}.json"
            _write_json(checkpoint_path, _checkpoint_payload(stats, mode=mode, db_path=str(db_path)))
            _emit_progress(config, stats, event="checkpoint")

    if config.execute:
        conn.commit()
        if stats.processed % config.commit_every != 0 and stats.processed > 0:
            stats.committed_batches += 1
            _emit_progress(config, stats, event="commit")

    summary = _checkpoint_payload(stats, mode=mode, db_path=str(db_path))
    summary["artifact_paths"] = {
        "summary": str(artifacts_dir / f"backfill_v3_summary_{stamp}.json"),
    }
    summary_path = artifacts_dir / f"backfill_v3_summary_{stamp}.json"
    _write_json(summary_path, summary)
    return summary


def default_artifacts_dir() -> Path:
    return Path(env_paths.get_artifacts_dir())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill v3 asset/identity/link rows from legacy file inventory."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite DB (defaults to TAGSLUT_DB)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes (default: dry-run)",
    )
    parser.add_argument(
        "--resume-from-file-id",
        type=int,
        default=0,
        help="Resume processing after the given files.rowid",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of rows to process",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=500,
        help="Commit every N processed rows in execute mode",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=500,
        help="Write a checkpoint artifact every N processed rows",
    )
    parser.add_argument(
        "--busy-timeout-ms",
        type=int,
        default=10_000,
        help="SQLite busy timeout in milliseconds",
    )
    parser.add_argument(
        "--abort-error-rate",
        type=float,
        default=50.0,
        help="Abort when errors per 1000 processed rows exceed this threshold",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print exception traceback on error",
    )
    args = parser.parse_args(argv)

    db_path_arg = args.db
    if db_path_arg is None:
        env_db = os.environ.get("TAGSLUT_DB")
        if env_db:
            db_path_arg = Path(env_db)
    if db_path_arg is None:
        print("error: --db is required unless TAGSLUT_DB is set")
        return 1

    db_path = db_path_arg.expanduser().resolve()
    config = BackfillConfig(
        execute=bool(args.execute),
        resume_from_file_id=args.resume_from_file_id,
        commit_every=args.commit_every,
        checkpoint_every=args.checkpoint_every,
        busy_timeout_ms=args.busy_timeout_ms,
        abort_error_rate_per_1000=args.abort_error_rate,
        artifacts_dir=default_artifacts_dir(),
        limit=args.limit,
        verbose=bool(args.verbose),
    )

    try:
        if args.verbose:
            mode = "execute" if config.execute else "dry_run"
            print(
                f"starting backfill_identity mode={mode} db={db_path} "
                f"resume_from_file_id={config.resume_from_file_id} limit={config.limit}",
                file=sys.stderr,
                flush=True,
            )
        conn = sqlite3.connect(str(db_path))
        summary = backfill_v3_identity_links(conn, db_path=db_path, config=config)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr, flush=True)
        if args.verbose:
            traceback.print_exc()
        return 1
    finally:
        if "conn" in locals():
            conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
