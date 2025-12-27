"""Reusable database queries for dedupe."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from dedupe.storage.schema import LIBRARY_TABLE, PICARD_MOVES_TABLE
from dedupe.utils import normalise_path


def fetch_records_by_state(
    connection: sqlite3.Connection,
    state: str,
) -> list[sqlite3.Row]:
    """Return rows in ``library_files`` filtered by *state*."""

    cursor = connection.execute(
        f"SELECT * FROM {LIBRARY_TABLE} WHERE library_state = ?",
        (state,),
    )
    return cursor.fetchall()


def upsert_library_rows(
    connection: sqlite3.Connection,
    payload: Iterable[dict[str, Any]],
) -> None:
    """Insert or update records in ``library_files`` from *payload*."""

    rows = []
    for entry in payload:
        entry = dict(entry)
        entry["path"] = normalise_path(str(entry["path"]))
        rows.append(entry)

    connection.executemany(
        f"""
        INSERT INTO {LIBRARY_TABLE} (
            path,
            size_bytes,
            mtime,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            channels,
            bit_depth,
            tags_json,
            fingerprint,
            fingerprint_duration,
            dup_group,
            duplicate_rank,
            is_canonical,
            extra_json,
            library_state,
            flac_ok
        ) VALUES (
            :path,
            :size_bytes,
            :mtime,
            :checksum,
            :duration,
            :sample_rate,
            :bit_rate,
            :channels,
            :bit_depth,
            :tags_json,
            :fingerprint,
            :fingerprint_duration,
            :dup_group,
            :duplicate_rank,
            :is_canonical,
            :extra_json,
            :library_state,
            :flac_ok
        )
        ON CONFLICT(path) DO UPDATE SET
            size_bytes=excluded.size_bytes,
            mtime=excluded.mtime,
            checksum=excluded.checksum,
            duration=excluded.duration,
            sample_rate=excluded.sample_rate,
            bit_rate=excluded.bit_rate,
            channels=excluded.channels,
            bit_depth=excluded.bit_depth,
            tags_json=excluded.tags_json,
            fingerprint=excluded.fingerprint,
            fingerprint_duration=excluded.fingerprint_duration,
            dup_group=excluded.dup_group,
            duplicate_rank=excluded.duplicate_rank,
            is_canonical=excluded.is_canonical,
            extra_json=excluded.extra_json,
            library_state=excluded.library_state,
            flac_ok=excluded.flac_ok
        """,
        rows,
    )


def update_library_path(
    connection: sqlite3.Connection,
    old_path: Path,
    new_path: Path,
    *,
    library_state: str | None = None,
) -> None:
    """Update a library file path, optionally enforcing *library_state*."""

    old_value = normalise_path(str(old_path))
    new_value = normalise_path(str(new_path))
    if library_state is None:
        connection.execute(
            f"UPDATE {LIBRARY_TABLE} SET path = ? WHERE path = ?",
            (new_value, old_value),
        )
        return

    connection.execute(
        f"UPDATE {LIBRARY_TABLE} SET path = ? WHERE path = ? AND library_state = ?",
        (new_value, old_value, library_state),
    )


def record_picard_move(
    connection: sqlite3.Connection,
    old_path: Path,
    new_path: Path,
    checksum: str | None,
) -> None:
    """Record a Picard move in the ``picard_moves`` table."""

    connection.execute(
        f"INSERT INTO {PICARD_MOVES_TABLE} (old_path, new_path, checksum, moved_at)"
        " VALUES (?, ?, ?, ?)",
        (
            normalise_path(str(old_path)),
            normalise_path(str(new_path)),
            checksum,
            time.time(),
        ),
    )


def extract_tags(tags_json: str | None) -> dict[str, Any]:
    """Decode tags JSON for validation helpers."""

    if not tags_json:
        return {}
    try:
        return json.loads(tags_json)
    except json.JSONDecodeError:
        return {}
