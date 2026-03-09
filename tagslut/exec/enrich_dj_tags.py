"""Compatibility wrapper for DJ snapshot resolution.

This module preserves the old function name while routing callers to the
database-driven DJ snapshot service. It does not mutate FLAC files or
canonical identity fields.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot_for_path

logger = logging.getLogger(__name__)

__all__ = ["enrich_dj_tags"]


def enrich_dj_tags(
    conn: sqlite3.Connection,
    flac_path: str | Path,
    *,
    dry_run: bool = False,
    essentia_binary: str = "essentia_streaming_extractor_music",
) -> dict[str, str | None]:
    flac_path_obj = Path(flac_path)
    snapshot = resolve_dj_tag_snapshot_for_path(
        conn,
        flac_path_obj,
        run_essentia=True,
        essentia_binary=essentia_binary,
        dry_run=dry_run,
    )
    if snapshot is None:
        logger.warning("no identity link for %s, skipping enrichment", flac_path_obj)
        return {}
    return {
        "bpm": snapshot.bpm,
        "key": snapshot.musical_key,
        "energy": str(snapshot.energy_1_10) if snapshot.energy_1_10 is not None else None,
    }
