#!/usr/bin/env python3
"""Migrate a tagslut v2 DB into standalone v3 schema tables."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.db import open_db_v3
from tagslut.storage.v3.schema import create_schema_v3

DEFAULT_BATCH_SIZE = 5000
PROGRESS_TABLE = "migration_progress"
CORE_TABLES = (
    "asset_file",
    "track_identity",
    "asset_link",
    "library_track_sources",
    "move_plan",
    "move_execution",
    "provenance_event",
)
EXPECTED_V2_FILES_COLUMNS_STRICT = {
    "path",
    "sha256",
    "streaminfo_md5",
    "checksum",
    "size",
    "mtime",
    "duration",
    "sample_rate",
    "bit_depth",
    "bitrate",
    "library",
    "zone",
    "flac_ok",
    "integrity_state",
    "integrity_checked_at",
    "sha256_checked_at",
    "streaminfo_checked_at",
    "duration_measured_ms",
    "download_source",
    "download_date",
    "mgmt_status",
    "canonical_isrc",
    "isrc",
    "beatport_id",
    "canonical_artist",
    "canonical_title",
}
PROVIDER_ID_COLUMNS = (
    # "spotify_id",  # purged
    "tidal_id",
    # "qobuz_id",  # purged
    "apple_music_id",
    "itunes_id",
    "deezer_id",
    "traxsource_id",
    "musicbrainz_id",
    "beatport_id",
)


@dataclass
class MigrationStats:
    assets_migrated: int = 0
    identities_created: int = 0
    unidentified_count: int = 0
    integrity_preserved_count: int = 0
    enrichment_preserved_count: int = 0
    last_v2_rowid: int = 0
    last_v2_path: str | None = None
    library_sources_done: bool = False
    move_tables_done: bool = False
    is_complete: bool = False

    @classmethod
    def from_progress_row(cls, row: sqlite3.Row) -> "MigrationStats":
        return cls(
            assets_migrated=int(row["assets_migrated"] or 0),
            identities_created=int(row["identities_created"] or 0),
            unidentified_count=int(row["unidentified_count"] or 0),
            integrity_preserved_count=int(row["integrity_preserved_count"] or 0),
            enrichment_preserved_count=int(row["enrichment_preserved_count"] or 0),
            last_v2_rowid=int(row["last_v2_rowid"] or 0),
            last_v2_path=(str(row["last_v2_path"]) if row["last_v2_path"] is not None else None),
            library_sources_done=bool(row["library_sources_done"]),
            move_tables_done=bool(row["move_tables_done"]),
            is_complete=bool(row["is_complete"]),
        )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {str(row[1]) for row in rows}


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return " ".join(text.split()).lower()


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _duration_measured_ms(row: dict[str, Any]) -> int | None:
    measured = _to_int(row.get("duration_measured_ms"))
    if measured is not None:
        return measured
    duration_s = _to_float(row.get("duration"))
    if duration_s is None:
        return None
    return int(round(duration_s * 1000.0))


def _duration_bucket_seconds(row: dict[str, Any]) -> int | None:
    measured_ms = _duration_measured_ms(row)
    if measured_ms is None:
        return None
    seconds = int(round(measured_ms / 1000.0))
    # Bucket to 5-second windows to keep text identities stable.
    return int(round(seconds / 5.0) * 5)


def _compute_identity_key(row: dict[str, Any]) -> tuple[str, bool, str | None, str | None]:
    canonical_isrc = _norm_text(row.get("canonical_isrc"))
    plain_isrc = _norm_text(row.get("isrc"))
    isrc = (canonical_isrc or plain_isrc)
    if isrc:
        isrc_norm = isrc.upper()
        return (f"isrc:{isrc_norm}", False, isrc_norm, None)

    beatport_id = _norm_text(row.get("beatport_id"))
    if beatport_id:
        return (f"beatport:{beatport_id}", False, None, beatport_id)

    artist_norm = _norm_name(row.get("canonical_artist"))
    title_norm = _norm_name(row.get("canonical_title"))
    duration_bucket = _duration_bucket_seconds(row)
    if artist_norm and title_norm and duration_bucket is not None:
        return (f"text:{artist_norm}|{title_norm}|{duration_bucket}s", False, None, None)

    token = (
        _norm_text(row.get("sha256"))
        or _norm_text(row.get("streaminfo_md5"))
        or _norm_text(row.get("checksum"))
        or _norm_text(row.get("path"))
        or "unknown"
    )
    return (f"unidentified:{token}", True, None, None)


def _collect_canonical_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in row.items():
        if not key.startswith("canonical_"):
            continue
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            payload[key] = stripped
        else:
            payload[key] = value
    return payload


def _upsert_asset_file(conn: sqlite3.Connection, row: dict[str, Any]) -> int:
    payload = {
        "content_sha256": _norm_text(row.get("sha256")),
        "streaminfo_md5": _norm_text(row.get("streaminfo_md5")),
        "checksum": _norm_text(row.get("checksum")),
        "size_bytes": _to_int(row.get("size")),
        "mtime": _to_float(row.get("mtime")),
        "duration_s": _to_float(row.get("duration")),
        "duration_measured_ms": _duration_measured_ms(row),
        "sample_rate": _to_int(row.get("sample_rate")),
        "bit_depth": _to_int(row.get("bit_depth")),
        "bitrate": _to_int(row.get("bitrate")),
        "library": _norm_text(row.get("library")),
        "zone": _norm_text(row.get("zone")),
        "download_source": _norm_text(row.get("download_source")),
        "download_date": _norm_text(row.get("download_date")),
        "mgmt_status": _norm_text(row.get("mgmt_status")),
        "flac_ok": _to_int(row.get("flac_ok")),
        "integrity_state": _norm_text(row.get("integrity_state")),
        "integrity_checked_at": _norm_text(row.get("integrity_checked_at")),
        "sha256_checked_at": _norm_text(row.get("sha256_checked_at")),
        "streaminfo_checked_at": _norm_text(row.get("streaminfo_checked_at")),
    }

    columns = ["path", *payload.keys()]
    values = [_norm_text(row.get("path")), *payload.values()]
    update_clause = ", ".join(f"{col}=excluded.{col}" for col in payload)
    conn.execute(
        f"""
        INSERT INTO asset_file ({", ".join(columns)})
        VALUES ({", ".join("?" for _ in columns)})
        ON CONFLICT(path) DO UPDATE SET
            {update_clause},
            last_seen_at=CURRENT_TIMESTAMP
        """,
        values,
    )
    found = conn.execute("SELECT id FROM asset_file WHERE path = ?", (_norm_text(row.get("path")),)).fetchone()
    if not found:
        raise RuntimeError(f"Failed to upsert asset_file row: {row.get('path')}")
    return int(found[0])


def _upsert_track_identity(
    conn: sqlite3.Connection,
    *,
    identity_key: str,
    row: dict[str, Any],
    computed_isrc: str | None,
    computed_beatport_id: str | None,
) -> tuple[int, bool]:
    canonical_payload = _collect_canonical_payload(row)
    payload: dict[str, Any] = {
        "isrc": computed_isrc or _norm_text(row.get("isrc")),
        "beatport_id": computed_beatport_id or _norm_text(row.get("beatport_id")),
        "tidal_id": _norm_text(row.get("tidal_id")),
        # "qobuz_id": _norm_text(row.get("qobuz_id")),  # purged
        # "spotify_id": _norm_text(row.get("spotify_id")),  # purged
        "apple_music_id": _norm_text(row.get("apple_music_id")),
        "deezer_id": _norm_text(row.get("deezer_id")),
        "traxsource_id": _norm_text(row.get("traxsource_id")),
        "itunes_id": _norm_text(row.get("itunes_id")),
        "musicbrainz_id": _norm_text(row.get("musicbrainz_id")),
        "artist_norm": _norm_name(row.get("canonical_artist")),
        "title_norm": _norm_name(row.get("canonical_title")),
        "album_norm": _norm_name(row.get("canonical_album")),
        "canonical_title": _norm_text(row.get("canonical_title")),
        "canonical_artist": _norm_text(row.get("canonical_artist")),
        "canonical_album": _norm_text(row.get("canonical_album")),
        "canonical_genre": _norm_text(row.get("canonical_genre")),
        "canonical_sub_genre": _norm_text(row.get("canonical_sub_genre")),
        "canonical_label": _norm_text(row.get("canonical_label")),
        "canonical_catalog_number": _norm_text(row.get("canonical_catalog_number")),
        "canonical_mix_name": _norm_text(row.get("canonical_mix_name")),
        "canonical_duration": _to_float(row.get("canonical_duration")),
        "canonical_year": _to_int(row.get("canonical_year")),
        "canonical_release_date": _norm_text(row.get("canonical_release_date")),
        "canonical_bpm": _to_float(row.get("canonical_bpm")),
        "canonical_key": _norm_text(row.get("canonical_key")),
        "canonical_payload_json": _json_dump(canonical_payload) if canonical_payload else None,
        "enriched_at": _norm_text(row.get("enriched_at")),
        "duration_ref_ms": _duration_measured_ms(row),
        "ref_source": "v2_migration",
        "ingested_at": _norm_text(row.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        "ingestion_method": "migration",
        "ingestion_source": "v2_migration",
        "ingestion_confidence": "legacy",
    }

    insert_cols = ["identity_key", *[c for c, v in payload.items() if v is not None]]
    insert_vals = [identity_key, *[payload[c] for c in payload if payload[c] is not None]]
    cur = conn.execute(
        f"""
        INSERT OR IGNORE INTO track_identity ({", ".join(insert_cols)})
        VALUES ({", ".join("?" for _ in insert_cols)})
        """,
        insert_vals,
    )
    created = bool(cur.rowcount)

    update_cols = [c for c, v in payload.items() if v is not None]
    if update_cols:
        conn.execute(
            f"""
            UPDATE track_identity
            SET {", ".join(f"{c}=COALESCE({c}, ?)" for c in update_cols)},
                updated_at=CURRENT_TIMESTAMP
            WHERE identity_key = ?
            """,
            [payload[c] for c in update_cols] + [identity_key],
        )

    found = conn.execute(
        "SELECT id FROM track_identity WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    if not found:
        raise RuntimeError(f"Failed to upsert track_identity row: {identity_key}")
    return int(found[0]), created


def _upsert_asset_link(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    identity_id: int,
    confidence: float,
    link_source: str,
) -> None:
    conn.execute(
        """
        INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(asset_id) DO UPDATE SET
            identity_id=excluded.identity_id,
            confidence=excluded.confidence,
            link_source=excluded.link_source,
            active=1,
            updated_at=CURRENT_TIMESTAMP
        """,
        (asset_id, identity_id, confidence, link_source),
    )


def _ensure_progress_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PROGRESS_TABLE} (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            v2_path TEXT NOT NULL,
            v3_path TEXT NOT NULL,
            batch_size INTEGER NOT NULL,
            last_v2_rowid INTEGER NOT NULL DEFAULT 0,
            last_v2_path TEXT,
            assets_migrated INTEGER NOT NULL DEFAULT 0,
            identities_created INTEGER NOT NULL DEFAULT 0,
            unidentified_count INTEGER NOT NULL DEFAULT 0,
            integrity_preserved_count INTEGER NOT NULL DEFAULT 0,
            enrichment_preserved_count INTEGER NOT NULL DEFAULT 0,
            library_sources_done INTEGER NOT NULL DEFAULT 0,
            move_tables_done INTEGER NOT NULL DEFAULT 0,
            is_complete INTEGER NOT NULL DEFAULT 0,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )


def _migration_has_data(conn: sqlite3.Connection) -> bool:
    for table in CORE_TABLES:
        if not _table_exists(conn, table):
            continue
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row and int(row[0]) > 0:
            return True
    return False


def _load_progress(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(f"SELECT * FROM {PROGRESS_TABLE} WHERE id = 1").fetchone()


def _reset_progress(
    conn: sqlite3.Connection,
    *,
    v2_path: Path,
    v3_path: Path,
    batch_size: int,
) -> None:
    conn.execute(f"DELETE FROM {PROGRESS_TABLE} WHERE id = 1")
    conn.execute(
        f"""
        INSERT INTO {PROGRESS_TABLE} (
            id, v2_path, v3_path, batch_size,
            last_v2_rowid, assets_migrated, identities_created, unidentified_count,
            integrity_preserved_count, enrichment_preserved_count,
            library_sources_done, move_tables_done, is_complete
        )
        VALUES (1, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0)
        """,
        (str(v2_path), str(v3_path), int(batch_size)),
    )


def _save_progress(conn: sqlite3.Connection, stats: MigrationStats) -> None:
    conn.execute(
        f"""
        UPDATE {PROGRESS_TABLE}
        SET last_v2_rowid = ?,
            last_v2_path = ?,
            assets_migrated = ?,
            identities_created = ?,
            unidentified_count = ?,
            integrity_preserved_count = ?,
            enrichment_preserved_count = ?,
            library_sources_done = ?,
            move_tables_done = ?,
            is_complete = ?,
            completed_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE completed_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
        """,
        (
            stats.last_v2_rowid,
            stats.last_v2_path,
            stats.assets_migrated,
            stats.identities_created,
            stats.unidentified_count,
            stats.integrity_preserved_count,
            stats.enrichment_preserved_count,
            1 if stats.library_sources_done else 0,
            1 if stats.move_tables_done else 0,
            1 if stats.is_complete else 0,
            1 if stats.is_complete else 0,
        ),
    )


def _ensure_identity_exists(
    conn: sqlite3.Connection,
    identity_key: str,
    *,
    provider: str | None = None,
    provider_track_id: str | None = None,
) -> bool:
    row = conn.execute(
        "SELECT id FROM track_identity WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    if row:
        return False

    payload: dict[str, Any] = {}
    if identity_key.startswith("isrc:"):
        payload["isrc"] = identity_key.split(":", 1)[1]
    elif identity_key.startswith("beatport:"):
        payload["beatport_id"] = identity_key.split(":", 1)[1]

    payload["ref_source"] = "v2_migration_source_snapshot"
    payload["ingested_at"] = datetime.now(timezone.utc).isoformat()
    payload["ingestion_method"] = "migration"
    payload["ingestion_source"] = "v2_migration_source_snapshot"
    payload["ingestion_confidence"] = "legacy"
    if provider and provider_track_id:
        payload["canonical_payload_json"] = _json_dump(
            {"source_provider": provider, "source_track_id": provider_track_id}
        )

    insert_cols = ["identity_key", *payload.keys()]
    conn.execute(
        f"""
        INSERT INTO track_identity ({", ".join(insert_cols)})
        VALUES ({", ".join("?" for _ in insert_cols)})
        """,
        [identity_key, *payload.values()],
    )
    return True


def _resolve_source_identity_key(
    conn: sqlite3.Connection,
    row: dict[str, Any],
    library_track_map: dict[str, str],
) -> str:
    library_track_key = _norm_text(row.get("library_track_key"))
    if library_track_key and library_track_key in library_track_map:
        return library_track_map[library_track_key]

    if library_track_key:
        existing = conn.execute(
            "SELECT 1 FROM track_identity WHERE identity_key = ?",
            (library_track_key,),
        ).fetchone()
        if existing:
            return library_track_key

    src_isrc = _norm_text(row.get("isrc"))
    if src_isrc:
        return f"isrc:{src_isrc.upper()}"

    provider = _norm_text(row.get("service")) or _norm_text(row.get("provider")) or "unknown"
    provider_track_id = _norm_text(row.get("service_track_id")) or _norm_text(row.get("provider_track_id"))
    if provider.lower() == "beatport" and provider_track_id:
        return f"beatport:{provider_track_id}"
    if library_track_key:
        return library_track_key
    if provider_track_id:
        return f"unidentified:source:{provider}:{provider_track_id}"
    return "unidentified:source:unknown"


def _migrate_library_track_sources(
    v2_conn: sqlite3.Connection,
    v3_conn: sqlite3.Connection,
    *,
    library_track_map: dict[str, str],
    strict: bool,
) -> tuple[int, int]:
    if not _table_exists(v2_conn, "library_track_sources"):
        return (0, 0)

    inserted = 0
    new_identities = 0
    rows = v2_conn.execute("SELECT rowid AS v2_rowid, * FROM library_track_sources ORDER BY rowid").fetchall()
    for src in rows:
        row = dict(src)
        provider = _norm_text(row.get("service")) or _norm_text(row.get("provider"))
        provider_track_id = _norm_text(row.get("service_track_id")) or _norm_text(row.get("provider_track_id"))
        if not provider or not provider_track_id:
            if strict:
                raise RuntimeError(
                    "library_track_sources row missing provider/service or provider_track_id/service_track_id"
                )
            continue

        identity_key = _resolve_source_identity_key(v3_conn, row, library_track_map)
        if _ensure_identity_exists(
            v3_conn,
            identity_key,
            provider=provider,
            provider_track_id=provider_track_id,
        ):
            new_identities += 1

        trace_payload: dict[str, Any] = {
            "v2_rowid": row.get("v2_rowid"),
            "v2_library_track_key": row.get("library_track_key"),
            "v2_service": row.get("service"),
            "v2_service_track_id": row.get("service_track_id"),
        }
        metadata_raw = _norm_text(row.get("metadata_json"))
        if metadata_raw:
            trace_payload["v2_metadata_json"] = metadata_raw

        v3_conn.execute(
            """
            INSERT INTO library_track_sources (
                identity_key,
                provider,
                provider_track_id,
                source_url,
                match_confidence,
                raw_payload_json,
                metadata_json,
                fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(identity_key, provider, provider_track_id) DO UPDATE SET
                source_url = COALESCE(excluded.source_url, source_url),
                match_confidence = COALESCE(excluded.match_confidence, match_confidence),
                raw_payload_json = COALESCE(excluded.raw_payload_json, raw_payload_json),
                metadata_json = COALESCE(excluded.metadata_json, metadata_json),
                fetched_at = COALESCE(excluded.fetched_at, fetched_at)
            """,
            (
                identity_key,
                provider,
                provider_track_id,
                _norm_text(row.get("url")) or _norm_text(row.get("source_url")),
                _norm_text(row.get("match_confidence")),
                metadata_raw,
                _json_dump(trace_payload),
                _norm_text(row.get("fetched_at")),
            ),
        )
        inserted += 1

    return (inserted, new_identities)


def _build_asset_id_map(
    v2_conn: sqlite3.Connection, v3_conn: sqlite3.Connection
) -> tuple[dict[int, int], dict[str, int]]:
    new_by_path: dict[str, int] = {
        str(row["path"]): int(row["id"])
        for row in v3_conn.execute("SELECT id, path FROM asset_file")
        if row["path"] is not None
    }
    mapped: dict[int, int] = {}
    if not _table_exists(v2_conn, "asset_file"):
        return mapped, new_by_path
    src_cols = _get_columns(v2_conn, "asset_file")
    if "id" not in src_cols or "path" not in src_cols:
        return mapped, new_by_path
    for row in v2_conn.execute("SELECT id, path FROM asset_file"):
        old_id = _to_int(row[0])
        path = _norm_text(row[1])
        if old_id is None or not path:
            continue
        if path in new_by_path:
            mapped[old_id] = new_by_path[path]
    return mapped, new_by_path


def _build_identity_id_map(v2_conn: sqlite3.Connection, v3_conn: sqlite3.Connection) -> dict[int, int]:
    mapped: dict[int, int] = {}
    if not _table_exists(v2_conn, "track_identity"):
        return mapped
    src_cols = _get_columns(v2_conn, "track_identity")
    if "id" not in src_cols or "identity_key" not in src_cols:
        return mapped
    target_by_key: dict[str, int] = {
        str(row["identity_key"]): int(row["id"])
        for row in v3_conn.execute("SELECT id, identity_key FROM track_identity")
    }
    for row in v2_conn.execute("SELECT id, identity_key FROM track_identity"):
        old_id = _to_int(row[0])
        key = _norm_text(row[1])
        if old_id is None or not key:
            continue
        new_id = target_by_key.get(key)
        if new_id is not None:
            mapped[old_id] = new_id
    return mapped


def _copy_move_plan(v2_conn: sqlite3.Connection, v3_conn: sqlite3.Connection) -> int:
    if not _table_exists(v2_conn, "move_plan"):
        return 0
    src_cols = [row[1] for row in v2_conn.execute("PRAGMA table_info(move_plan)").fetchall()]
    dst_cols = _get_columns(v3_conn, "move_plan")
    columns = [c for c in src_cols if c in dst_cols]
    if not columns:
        return 0

    inserted = 0
    rows = v2_conn.execute(f"SELECT {', '.join(columns)} FROM move_plan ORDER BY id").fetchall()
    for row in rows:
        v3_conn.execute(
            f"""
            INSERT OR IGNORE INTO move_plan ({", ".join(columns)})
            VALUES ({", ".join("?" for _ in columns)})
            """,
            list(row),
        )
        inserted += 1
    return inserted


def _copy_move_execution(
    v2_conn: sqlite3.Connection,
    v3_conn: sqlite3.Connection,
    *,
    asset_id_map: dict[int, int],
    asset_path_map: dict[str, int],
    strict: bool,
) -> int:
    if not _table_exists(v2_conn, "move_execution"):
        return 0
    src_cols = [row[1] for row in v2_conn.execute("PRAGMA table_info(move_execution)").fetchall()]
    dst_cols = _get_columns(v3_conn, "move_execution")
    columns = [c for c in src_cols if c in dst_cols]
    if not columns:
        return 0

    inserted = 0
    rows = v2_conn.execute(f"SELECT {', '.join(columns)} FROM move_execution ORDER BY id").fetchall()
    for raw in rows:
        data = {columns[i]: raw[i] for i in range(len(columns))}
        old_asset_id = _to_int(data.get("asset_id"))
        new_asset_id = asset_id_map.get(old_asset_id) if old_asset_id is not None else None
        if new_asset_id is None:
            source_path = _norm_text(data.get("source_path"))
            dest_path = _norm_text(data.get("dest_path"))
            if source_path and source_path in asset_path_map:
                new_asset_id = asset_path_map[source_path]
            elif dest_path and dest_path in asset_path_map:
                new_asset_id = asset_path_map[dest_path]
        if "asset_id" in data:
            data["asset_id"] = new_asset_id

        values = [data[c] for c in columns]
        sql = (
            f"INSERT OR IGNORE INTO move_execution ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        try:
            v3_conn.execute(sql, values)
        except sqlite3.IntegrityError as exc:
            if strict:
                raise RuntimeError(f"Failed to copy move_execution row: {exc}") from exc
            data["asset_id"] = None
            if "plan_id" in data:
                data["plan_id"] = None
            v3_conn.execute(sql, [data[c] for c in columns])
        inserted += 1
    return inserted


def _copy_provenance_event(
    v2_conn: sqlite3.Connection,
    v3_conn: sqlite3.Connection,
    *,
    asset_id_map: dict[int, int],
    identity_id_map: dict[int, int],
    strict: bool,
) -> int:
    if not _table_exists(v2_conn, "provenance_event"):
        return 0
    src_cols = [row[1] for row in v2_conn.execute("PRAGMA table_info(provenance_event)").fetchall()]
    dst_cols = _get_columns(v3_conn, "provenance_event")
    columns = [c for c in src_cols if c in dst_cols]
    if not columns:
        return 0

    inserted = 0
    rows = v2_conn.execute(f"SELECT {', '.join(columns)} FROM provenance_event ORDER BY id").fetchall()
    for raw in rows:
        data = {columns[i]: raw[i] for i in range(len(columns))}
        if "asset_id" in data:
            old_asset_id = _to_int(data.get("asset_id"))
            data["asset_id"] = asset_id_map.get(old_asset_id) if old_asset_id is not None else None
        if "identity_id" in data:
            old_identity_id = _to_int(data.get("identity_id"))
            data["identity_id"] = identity_id_map.get(old_identity_id) if old_identity_id is not None else None

        values = [data[c] for c in columns]
        sql = (
            f"INSERT OR IGNORE INTO provenance_event ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})"
        )
        try:
            v3_conn.execute(sql, values)
        except sqlite3.IntegrityError as exc:
            if strict:
                raise RuntimeError(f"Failed to copy provenance_event row: {exc}") from exc
            if "move_execution_id" in data:
                data["move_execution_id"] = None
            if "move_plan_id" in data:
                data["move_plan_id"] = None
            if "asset_id" in data:
                data["asset_id"] = None
            if "identity_id" in data:
                data["identity_id"] = None
            v3_conn.execute(sql, [data[c] for c in columns])
        inserted += 1
    return inserted


def _build_library_track_map(v2_conn: sqlite3.Connection) -> dict[str, str]:
    if not _table_exists(v2_conn, "files"):
        return {}
    cols = _get_columns(v2_conn, "files")
    if "library_track_key" not in cols:
        return {}
    select_cols = ["library_track_key", "path", "sha256", "streaminfo_md5", "checksum", "duration"]
    for optional in ("duration_measured_ms", "canonical_isrc", "isrc", "beatport_id", "canonical_artist", "canonical_title"):
        if optional in cols and optional not in select_cols:
            select_cols.append(optional)
    mapping: dict[str, str] = {}
    rows = v2_conn.execute(f"SELECT {', '.join(select_cols)} FROM files").fetchall()
    for raw in rows:
        row = {select_cols[i]: raw[i] for i in range(len(select_cols))}
        library_track_key = _norm_text(row.get("library_track_key"))
        if not library_track_key:
            continue
        identity_key, _, _, _ = _compute_identity_key(row)
        mapping.setdefault(library_track_key, identity_key)
    return mapping


def migrate_v2_to_v3(
    *,
    v2_path: Path,
    v3_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    resume: bool = False,
    dry_run: bool = False,
    strict: bool = False,
) -> dict[str, int]:
    if batch_size <= 0:
        raise RuntimeError("--batch-size must be > 0")

    src_path = v2_path.expanduser().resolve()
    if not src_path.exists():
        raise RuntimeError(f"v2 DB not found: {src_path}")

    if dry_run:
        dst_path = Path(":memory:")
    else:
        dst_path = v3_path.expanduser().resolve()

    v2_conn = sqlite3.connect(str(src_path))
    v2_conn.row_factory = sqlite3.Row

    v3_conn = open_db_v3(":memory:" if dry_run else dst_path, create=True)
    v3_conn.row_factory = sqlite3.Row

    try:
        create_schema_v3(v3_conn)
        _ensure_progress_table(v3_conn)

        if not _table_exists(v2_conn, "files"):
            raise RuntimeError("v2 DB does not contain required 'files' table")
        v2_files_cols = _get_columns(v2_conn, "files")
        if "path" not in v2_files_cols:
            raise RuntimeError("v2.files is missing required 'path' column")
        if strict:
            missing = sorted(EXPECTED_V2_FILES_COLUMNS_STRICT - v2_files_cols)
            if missing:
                raise RuntimeError(
                    "strict mode: v2.files missing required columns: " + ", ".join(missing)
                )

        stats = MigrationStats()
        if not dry_run:
            row = _load_progress(v3_conn)
            if resume:
                if row is None:
                    _reset_progress(v3_conn, v2_path=src_path, v3_path=dst_path, batch_size=batch_size)
                    v3_conn.commit()
                else:
                    old_v2 = _norm_text(row["v2_path"])
                    if old_v2 and old_v2 != str(src_path):
                        raise RuntimeError(
                            f"--resume requested, but progress was recorded for a different v2 DB: {old_v2}"
                        )
                    stats = MigrationStats.from_progress_row(row)
                    if stats.is_complete:
                        return {
                            "assets_migrated": stats.assets_migrated,
                            "identities_created": stats.identities_created,
                            "unidentified_count": stats.unidentified_count,
                            "integrity_preserved_count": stats.integrity_preserved_count,
                            "enrichment_preserved_count": stats.enrichment_preserved_count,
                        }
            else:
                if _migration_has_data(v3_conn):
                    raise RuntimeError(
                        "Target v3 DB already contains migration data. "
                        "Use --resume to continue or choose a new --v3 path."
                    )
                _reset_progress(v3_conn, v2_path=src_path, v3_path=dst_path, batch_size=batch_size)
                v3_conn.commit()

        canonical_cols = sorted(c for c in v2_files_cols if c.startswith("canonical_"))
        selected_cols: list[str] = [
            "path",
            "sha256",
            "streaminfo_md5",
            "checksum",
            "size",
            "mtime",
            "duration",
            "duration_measured_ms",
            "sample_rate",
            "bit_depth",
            "bitrate",
            "library",
            "zone",
            "download_source",
            "download_date",
            "mgmt_status",
            "enriched_at",
            "flac_ok",
            "integrity_state",
            "integrity_checked_at",
            "sha256_checked_at",
            "streaminfo_checked_at",
            "library_track_key",
            "isrc",
            "beatport_id",
            *PROVIDER_ID_COLUMNS,
            *canonical_cols,
        ]
        seen: set[str] = set()
        selected_cols = [c for c in selected_cols if c in v2_files_cols and not (c in seen or seen.add(c))]

        files_sql = (
            f"SELECT rowid AS v2_rowid, {', '.join(selected_cols)} "
            "FROM files WHERE rowid > ? ORDER BY rowid LIMIT ?"
        )

        library_track_map = _build_library_track_map(v2_conn)

        while True:
            batch_rows = v2_conn.execute(files_sql, (stats.last_v2_rowid, int(batch_size))).fetchall()
            if not batch_rows:
                break

            v3_conn.execute("BEGIN")
            try:
                for batch_row in batch_rows:
                    row = dict(batch_row)
                    path = _norm_text(row.get("path"))
                    if not path:
                        if strict:
                            raise RuntimeError("Encountered files row with empty path")
                        continue

                    asset_id = _upsert_asset_file(v3_conn, row)
                    identity_key, unidentified, computed_isrc, computed_beatport = _compute_identity_key(row)
                    identity_id, created = _upsert_track_identity(
                        v3_conn,
                        identity_key=identity_key,
                        row=row,
                        computed_isrc=computed_isrc,
                        computed_beatport_id=computed_beatport,
                    )
                    if created:
                        stats.identities_created += 1

                    if unidentified:
                        stats.unidentified_count += 1

                    confidence = 0.2 if unidentified else (1.0 if computed_isrc else 0.9 if computed_beatport else 0.7)
                    _upsert_asset_link(
                        v3_conn,
                        asset_id=asset_id,
                        identity_id=identity_id,
                        confidence=confidence,
                        link_source="v2_migration",
                    )

                    if any(
                        row.get(k) is not None
                        for k in (
                            "flac_ok",
                            "integrity_state",
                            "integrity_checked_at",
                            "sha256_checked_at",
                            "streaminfo_checked_at",
                        )
                    ):
                        stats.integrity_preserved_count += 1

                    canonical_payload = _collect_canonical_payload(row)
                    if canonical_payload:
                        stats.enrichment_preserved_count += 1

                    library_track_key = _norm_text(row.get("library_track_key"))
                    if library_track_key:
                        library_track_map.setdefault(library_track_key, identity_key)

                    stats.assets_migrated += 1
                    stats.last_v2_rowid = int(row["v2_rowid"])
                    stats.last_v2_path = path

                if not dry_run:
                    _save_progress(v3_conn, stats)
                v3_conn.commit()
            except Exception:
                v3_conn.rollback()
                raise

        if not stats.library_sources_done:
            v3_conn.execute("BEGIN")
            try:
                _, new_identities = _migrate_library_track_sources(
                    v2_conn,
                    v3_conn,
                    library_track_map=library_track_map,
                    strict=strict,
                )
                stats.identities_created += new_identities
                stats.library_sources_done = True
                if not dry_run:
                    _save_progress(v3_conn, stats)
                v3_conn.commit()
            except Exception:
                v3_conn.rollback()
                raise

        if not stats.move_tables_done:
            v3_conn.execute("BEGIN")
            try:
                _copy_move_plan(v2_conn, v3_conn)
                asset_id_map, asset_path_map = _build_asset_id_map(v2_conn, v3_conn)
                identity_id_map = _build_identity_id_map(v2_conn, v3_conn)
                _copy_move_execution(
                    v2_conn,
                    v3_conn,
                    asset_id_map=asset_id_map,
                    asset_path_map=asset_path_map,
                    strict=strict,
                )
                _copy_provenance_event(
                    v2_conn,
                    v3_conn,
                    asset_id_map=asset_id_map,
                    identity_id_map=identity_id_map,
                    strict=strict,
                )
                stats.move_tables_done = True
                if not dry_run:
                    _save_progress(v3_conn, stats)
                v3_conn.commit()
            except Exception:
                v3_conn.rollback()
                raise

        stats.is_complete = True
        if not dry_run:
            v3_conn.execute("BEGIN")
            try:
                _save_progress(v3_conn, stats)
                v3_conn.commit()
            except Exception:
                v3_conn.rollback()
                raise

        return {
            "assets_migrated": stats.assets_migrated,
            "identities_created": stats.identities_created,
            "unidentified_count": stats.unidentified_count,
            "integrity_preserved_count": stats.integrity_preserved_count,
            "enrichment_preserved_count": stats.enrichment_preserved_count,
        }
    finally:
        v2_conn.close()
        v3_conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate a v2 DB to standalone v3 schema.")
    parser.add_argument("--v2", required=True, type=Path, help="Path to source v2 DB")
    parser.add_argument("--v3", required=True, type=Path, help="Path to destination v3 DB")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows to commit per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from migration_progress")
    parser.add_argument("--dry-run", action="store_true", help="Run against an in-memory v3 DB")
    parser.add_argument("--strict", action="store_true", help="Fail on missing expected schema fields")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        summary = migrate_v2_to_v3(
            v2_path=args.v2,
            v3_path=args.v3,
            batch_size=int(args.batch_size),
            resume=bool(args.resume),
            dry_run=bool(args.dry_run),
            strict=bool(args.strict),
        )
    except RuntimeError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 2

    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    print(f"{mode}: v2 -> v3 migration complete")
    print(f"assets migrated: {summary['assets_migrated']}")
    print(f"identities created: {summary['identities_created']}")
    print(f"unidentified count: {summary['unidentified_count']}")
    print(f"integrity-preserved count: {summary['integrity_preserved_count']}")
    print(f"enrichment-preserved count: {summary['enrichment_preserved_count']}")
    if not args.dry_run:
        print(f"v3 DB: {args.v3.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
