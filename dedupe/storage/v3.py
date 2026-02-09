"""V3 dual-write helpers for migration.

These helpers keep v3 tables updated in parallel with legacy writes while the
migration flag is enabled.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from dedupe.storage.schema import (
    V3_ASSET_FILE_TABLE,
    V3_ASSET_LINK_TABLE,
    V3_MOVE_EXECUTION_TABLE,
    V3_MOVE_PLAN_TABLE,
    V3_PROVENANCE_EVENT_TABLE,
    V3_TRACK_IDENTITY_TABLE,
)
from dedupe.utils.config import get_config

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


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


def _lookup_tag(metadata: dict[str, Any] | None, keys: list[str]) -> str | None:
    if not metadata:
        return None
    lowered = {str(k).lower(): v for k, v in metadata.items()}
    for key in keys:
        if key.lower() in lowered:
            return _norm_text(lowered[key.lower()])
    return None


def dual_write_enabled() -> bool:
    """Return whether v3 dual-write is enabled."""

    env_value = os.getenv("DEDUPE_V3_DUAL_WRITE")
    if env_value is not None:
        lowered = env_value.strip().lower()
        if lowered in _TRUTHY:
            return True
        if lowered in _FALSY:
            return False

    config = get_config()
    return bool(
        config.get("dedupe.v3.dual_write", config.get("v3.dual_write", False))
    )


def resolve_asset_id_by_path(conn: sqlite3.Connection, path: str | Path) -> int | None:
    row = conn.execute(
        f"SELECT id FROM {V3_ASSET_FILE_TABLE} WHERE path = ?",
        (str(path),),
    ).fetchone()
    return int(row[0]) if row else None


def upsert_asset_file(
    conn: sqlite3.Connection,
    *,
    path: str | Path,
    content_sha256: str | None = None,
    streaminfo_md5: str | None = None,
    checksum: str | None = None,
    size_bytes: int | None = None,
    mtime: float | None = None,
    duration_s: float | None = None,
    sample_rate: int | None = None,
    bit_depth: int | None = None,
    bitrate: int | None = None,
    library: str | None = None,
    zone: str | None = None,
    download_source: str | None = None,
    download_date: str | None = None,
    mgmt_status: str | None = None,
) -> int:
    path_s = str(path)
    conn.execute(
        f"""
        INSERT INTO {V3_ASSET_FILE_TABLE} (
            path, content_sha256, streaminfo_md5, checksum, size_bytes, mtime,
            duration_s, sample_rate, bit_depth, bitrate, library, zone,
            download_source, download_date, mgmt_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            content_sha256 = excluded.content_sha256,
            streaminfo_md5 = excluded.streaminfo_md5,
            checksum = excluded.checksum,
            size_bytes = excluded.size_bytes,
            mtime = excluded.mtime,
            duration_s = excluded.duration_s,
            sample_rate = excluded.sample_rate,
            bit_depth = excluded.bit_depth,
            bitrate = excluded.bitrate,
            library = excluded.library,
            zone = excluded.zone,
            download_source = excluded.download_source,
            download_date = excluded.download_date,
            mgmt_status = excluded.mgmt_status,
            last_seen_at = CURRENT_TIMESTAMP
        """,
        (
            path_s,
            _norm_text(content_sha256),
            _norm_text(streaminfo_md5),
            _norm_text(checksum),
            size_bytes,
            mtime,
            duration_s,
            sample_rate,
            bit_depth,
            bitrate,
            _norm_text(library),
            _norm_text(zone),
            _norm_text(download_source),
            _norm_text(download_date),
            _norm_text(mgmt_status),
        ),
    )
    asset_id = resolve_asset_id_by_path(conn, path_s)
    if asset_id is None:
        raise RuntimeError(f"Failed to upsert asset row for path: {path_s}")
    return asset_id


def move_asset_path(
    conn: sqlite3.Connection,
    *,
    source_path: str | Path,
    dest_path: str | Path,
    update_fields: dict[str, Any] | None = None,
) -> int | None:
    src = str(source_path)
    dest = str(dest_path)

    src_id = resolve_asset_id_by_path(conn, src)
    if src_id is None:
        payload = dict(update_fields or {})
        payload["path"] = dest
        return upsert_asset_file(conn, **payload)

    dest_id = resolve_asset_id_by_path(conn, dest)
    if dest_id is not None and dest_id != src_id:
        if update_fields:
            upsert_asset_file(conn, path=dest, **update_fields)
        conn.execute(f"DELETE FROM {V3_ASSET_FILE_TABLE} WHERE id = ?", (src_id,))
        return dest_id

    # Update the existing row to the destination path and refresh metadata.
    fields = dict(update_fields or {})
    fields.setdefault("content_sha256", None)
    fields.setdefault("streaminfo_md5", None)
    fields.setdefault("checksum", None)
    fields.setdefault("size_bytes", None)
    fields.setdefault("mtime", None)
    fields.setdefault("duration_s", None)
    fields.setdefault("sample_rate", None)
    fields.setdefault("bit_depth", None)
    fields.setdefault("bitrate", None)
    fields.setdefault("library", None)
    fields.setdefault("zone", None)
    fields.setdefault("download_source", None)
    fields.setdefault("download_date", None)
    fields.setdefault("mgmt_status", None)

    conn.execute(
        f"""
        UPDATE {V3_ASSET_FILE_TABLE}
        SET path = ?,
            content_sha256 = COALESCE(?, content_sha256),
            streaminfo_md5 = COALESCE(?, streaminfo_md5),
            checksum = COALESCE(?, checksum),
            size_bytes = COALESCE(?, size_bytes),
            mtime = COALESCE(?, mtime),
            duration_s = COALESCE(?, duration_s),
            sample_rate = COALESCE(?, sample_rate),
            bit_depth = COALESCE(?, bit_depth),
            bitrate = COALESCE(?, bitrate),
            library = COALESCE(?, library),
            zone = COALESCE(?, zone),
            download_source = COALESCE(?, download_source),
            download_date = COALESCE(?, download_date),
            mgmt_status = COALESCE(?, mgmt_status),
            last_seen_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            dest,
            _norm_text(fields["content_sha256"]),
            _norm_text(fields["streaminfo_md5"]),
            _norm_text(fields["checksum"]),
            fields["size_bytes"],
            fields["mtime"],
            fields["duration_s"],
            fields["sample_rate"],
            fields["bit_depth"],
            fields["bitrate"],
            _norm_text(fields["library"]),
            _norm_text(fields["zone"]),
            _norm_text(fields["download_source"]),
            _norm_text(fields["download_date"]),
            _norm_text(fields["mgmt_status"]),
            src_id,
        ),
    )
    return resolve_asset_id_by_path(conn, dest)


def upsert_track_identity(
    conn: sqlite3.Connection,
    *,
    isrc: str | None,
    beatport_id: str | None,
    artist: str | None,
    title: str | None,
    duration_ref_ms: int | None = None,
    ref_source: str | None = None,
) -> int | None:
    isrc_norm = _norm_text(isrc)
    beatport_norm = _norm_text(beatport_id)
    artist_norm = _norm_name(artist)
    title_norm = _norm_name(title)

    identity_key: str | None = None
    if isrc_norm:
        identity_key = f"isrc:{isrc_norm.lower()}"
    elif beatport_norm:
        identity_key = f"beatport:{beatport_norm}"
    elif artist_norm and title_norm:
        identity_key = f"text:{artist_norm}|{title_norm}"

    if not identity_key:
        return None

    conn.execute(
        f"""
        INSERT INTO {V3_TRACK_IDENTITY_TABLE} (
            identity_key, isrc, beatport_id, artist_norm, title_norm, duration_ref_ms, ref_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(identity_key) DO UPDATE SET
            isrc = COALESCE(excluded.isrc, isrc),
            beatport_id = COALESCE(excluded.beatport_id, beatport_id),
            artist_norm = COALESCE(excluded.artist_norm, artist_norm),
            title_norm = COALESCE(excluded.title_norm, title_norm),
            duration_ref_ms = COALESCE(excluded.duration_ref_ms, duration_ref_ms),
            ref_source = COALESCE(excluded.ref_source, ref_source),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            identity_key,
            isrc_norm,
            beatport_norm,
            artist_norm,
            title_norm,
            duration_ref_ms,
            _norm_text(ref_source),
        ),
    )
    row = conn.execute(
        f"SELECT id FROM {V3_TRACK_IDENTITY_TABLE} WHERE identity_key = ?",
        (identity_key,),
    ).fetchone()
    return int(row[0]) if row else None


def upsert_asset_link(
    conn: sqlite3.Connection,
    *,
    asset_id: int,
    identity_id: int,
    confidence: float,
    link_source: str,
    active: bool = True,
) -> int:
    conn.execute(
        f"""
        INSERT INTO {V3_ASSET_LINK_TABLE} (
            asset_id, identity_id, confidence, link_source, active
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(asset_id, identity_id) DO UPDATE SET
            confidence = excluded.confidence,
            link_source = excluded.link_source,
            active = excluded.active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (asset_id, identity_id, confidence, link_source, 1 if active else 0),
    )
    row = conn.execute(
        f"SELECT id FROM {V3_ASSET_LINK_TABLE} WHERE asset_id = ? AND identity_id = ?",
        (asset_id, identity_id),
    ).fetchone()
    if not row:
        raise RuntimeError("Failed to upsert asset_link row")
    return int(row[0])


def ensure_move_plan(
    conn: sqlite3.Connection,
    *,
    plan_key: str,
    plan_type: str,
    plan_path: str | None,
    policy_version: str | None,
    context: dict[str, Any] | None = None,
) -> int:
    context_json = json.dumps(context or {}, sort_keys=True, separators=(",", ":"))
    conn.execute(
        f"""
        INSERT INTO {V3_MOVE_PLAN_TABLE} (
            plan_key, plan_type, plan_path, policy_version, context_json
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(plan_key) DO UPDATE SET
            plan_type = excluded.plan_type,
            plan_path = excluded.plan_path,
            policy_version = excluded.policy_version,
            context_json = excluded.context_json
        """,
        (
            _norm_text(plan_key),
            _norm_text(plan_type),
            _norm_text(plan_path),
            _norm_text(policy_version),
            context_json,
        ),
    )
    row = conn.execute(
        f"SELECT id FROM {V3_MOVE_PLAN_TABLE} WHERE plan_key = ?",
        (_norm_text(plan_key),),
    ).fetchone()
    if not row:
        raise RuntimeError(f"Failed to ensure move plan: {plan_key}")
    return int(row[0])


def insert_move_execution(
    conn: sqlite3.Connection,
    *,
    plan_id: int | None,
    asset_id: int | None,
    source_path: str | None,
    dest_path: str | None,
    action: str | None,
    status: str,
    verification: str | None,
    error: str | None,
    details: dict[str, Any] | None = None,
    executed_at: str | None = None,
) -> int:
    details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
    cursor = conn.execute(
        f"""
        INSERT INTO {V3_MOVE_EXECUTION_TABLE} (
            plan_id, asset_id, source_path, dest_path, action, status,
            verification, error, details_json, executed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
        """,
        (
            plan_id,
            asset_id,
            _norm_text(source_path),
            _norm_text(dest_path),
            _norm_text(action),
            _norm_text(status) or "unknown",
            _norm_text(verification),
            _norm_text(error),
            details_json,
            _norm_text(executed_at),
        ),
    )
    rowid = cursor.lastrowid
    if rowid is None:
        raise RuntimeError("Failed to insert move_execution row")
    return int(rowid)


def record_provenance_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    status: str | None = None,
    asset_id: int | None = None,
    identity_id: int | None = None,
    move_plan_id: int | None = None,
    move_execution_id: int | None = None,
    source_path: str | None = None,
    dest_path: str | None = None,
    details: dict[str, Any] | None = None,
    event_time: str | None = None,
) -> int:
    details_json = json.dumps(details or {}, sort_keys=True, separators=(",", ":"))
    cursor = conn.execute(
        f"""
        INSERT INTO {V3_PROVENANCE_EVENT_TABLE} (
            event_type, event_time, asset_id, identity_id, move_plan_id, move_execution_id,
            source_path, dest_path, status, details_json
        ) VALUES (?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _norm_text(event_type),
            _norm_text(event_time),
            asset_id,
            identity_id,
            move_plan_id,
            move_execution_id,
            _norm_text(source_path),
            _norm_text(dest_path),
            _norm_text(status),
            details_json,
        ),
    )
    rowid = cursor.lastrowid
    if rowid is None:
        raise RuntimeError("Failed to insert provenance_event row")
    return int(rowid)


def identity_hints_from_metadata(metadata: dict[str, Any] | None) -> dict[str, str | None]:
    """Extract identity hints from metadata dict."""

    isrc = _lookup_tag(metadata, ["isrc", "tsrc", "canonical_isrc"])
    beatport_id = _lookup_tag(
        metadata,
        ["beatport_track_id", "bp_track_id", "beatport_id", "beatport track id"],
    )
    artist = _lookup_tag(metadata, ["artist", "albumartist", "canonical_artist"])
    title = _lookup_tag(metadata, ["title", "canonical_title"])
    return {
        "isrc": isrc,
        "beatport_id": beatport_id,
        "artist": artist,
        "title": title,
    }


def dual_write_registered_file(
    conn: sqlite3.Connection,
    *,
    path: str | Path,
    content_sha256: str | None,
    streaminfo_md5: str | None,
    checksum: str | None,
    size_bytes: int | None,
    mtime: float | None,
    duration_s: float | None,
    sample_rate: int | None,
    bit_depth: int | None,
    bitrate: int | None,
    library: str | None,
    zone: str | None,
    download_source: str | None,
    download_date: str | None,
    mgmt_status: str | None,
    metadata: dict[str, Any] | None,
    duration_ref_ms: int | None,
    duration_ref_source: str | None,
    event_time: str | None = None,
) -> tuple[int, int | None]:
    asset_id = upsert_asset_file(
        conn,
        path=path,
        content_sha256=content_sha256,
        streaminfo_md5=streaminfo_md5,
        checksum=checksum,
        size_bytes=size_bytes,
        mtime=mtime,
        duration_s=duration_s,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        bitrate=bitrate,
        library=library,
        zone=zone,
        download_source=download_source,
        download_date=download_date,
        mgmt_status=mgmt_status,
    )

    identity_hints = identity_hints_from_metadata(metadata)
    identity_id = upsert_track_identity(
        conn,
        isrc=identity_hints["isrc"],
        beatport_id=identity_hints["beatport_id"],
        artist=identity_hints["artist"],
        title=identity_hints["title"],
        duration_ref_ms=duration_ref_ms,
        ref_source=duration_ref_source or download_source,
    )
    if identity_id is not None:
        upsert_asset_link(
            conn,
            asset_id=asset_id,
            identity_id=identity_id,
            confidence=1.0 if identity_hints["isrc"] else 0.8,
            link_source="register",
        )

    record_provenance_event(
        conn,
        event_type="registered",
        status=mgmt_status,
        asset_id=asset_id,
        identity_id=identity_id,
        source_path=str(path),
        details={"source": download_source},
        event_time=event_time,
    )
    return asset_id, identity_id
