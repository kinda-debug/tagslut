"""DJ XML emit helpers (DJ pipeline Stage 4).

Stage 4 emit/patch is implemented in `tagslut.dj.xml_emit`.
This module provides a stable import path for tooling and type-checking.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.dj.xml_emit import (
    emit_rekordbox_xml,
    patch_rekordbox_xml,
    repair_rekordbox_xml_patch_path,
)
from tagslut.storage.v3.dj_state import compute_dj_state_hash
from tagslut.cli._progress import ProgressCallback


def dj_state_hash(conn: sqlite3.Connection) -> str:
    """Expose the shared DJ state hash for callers and tests."""
    return compute_dj_state_hash(conn)


def emit_xml(
    conn: sqlite3.Connection,
    *,
    output_path: Path,
    playlist_scope: list[int] | None = None,
    skip_validation: bool = False,
    progress_cb: ProgressCallback | None = None,
) -> str:
    return emit_rekordbox_xml(
        conn,
        output_path=output_path,
        playlist_scope=playlist_scope,
        skip_validation=skip_validation,
        progress_cb=progress_cb,
    )


def patch_xml(
    conn: sqlite3.Connection,
    *,
    output_path: Path,
    prior_export_id: int | None = None,
    playlist_scope: list[int] | None = None,
    skip_validation: bool = False,
    progress_cb: ProgressCallback | None = None,
) -> str:
    return patch_rekordbox_xml(
        conn,
        output_path=output_path,
        prior_export_id=prior_export_id,
        playlist_scope=playlist_scope,
        skip_validation=skip_validation,
        progress_cb=progress_cb,
    )


def patch_repair(
    conn: sqlite3.Connection,
    *,
    xml_path: Path,
    prior_export_id: int | None = None,
) -> int:
    return repair_rekordbox_xml_patch_path(
        conn,
        xml_path=xml_path,
        prior_export_id=prior_export_id,
    )
