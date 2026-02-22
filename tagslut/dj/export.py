from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tagslut.dj.curation import (
    CurationResult,
    DjCurationConfig,
    filter_candidates,
    load_dj_curation_config,
)
from tagslut.dj.key_detection import detect_key, is_keyfinder_available
from tagslut.dj.transcode import TrackRow, transcode_one

log = logging.getLogger(__name__)


@dataclass
class ExportStats:
    total_candidates: int = 0
    passed_curation: int = 0
    rejected_curation: int = 0
    transcoded_ok: int = 0
    transcoded_skipped: int = 0
    transcoded_failed: int = 0
    keys_detected: int = 0
    keys_skipped: int = 0


@dataclass
class ExportPlan:
    """Result of a dry-run export — what would happen."""

    tracks: list[TrackRow] = field(default_factory=list)
    curation_result: CurationResult | None = None
    stats: ExportStats = field(default_factory=ExportStats)
    dry_run: bool = True


def plan_export(
    tracks: list[TrackRow],
    config: DjCurationConfig,
    output_root: Path,
) -> ExportPlan:
    """Dry-run: apply curation filters and build export plan without transcoding."""
    _ = output_root
    candidates = [
        {
            "artist": t.track_artist or t.album_artist,
            "duration_sec": None,
            "genre": None,
            "_track": t,
        }
        for t in tracks
    ]

    curation = filter_candidates(candidates, config)

    stats = ExportStats(
        total_candidates=len(tracks),
        passed_curation=len(curation.passed),
        rejected_curation=len(curation.rejected_blocklist)
        + len(curation.rejected_duration)
        + len(curation.rejected_genre),
    )

    passed_tracks = [c["_track"] for c in curation.passed]

    return ExportPlan(
        tracks=passed_tracks,
        curation_result=curation,
        stats=stats,
        dry_run=True,
    )


def run_export(
    tracks: list[TrackRow],
    config: DjCurationConfig,
    output_root: Path,
    *,
    jobs: int = 4,
    overwrite: bool = False,
    detect_keys: bool = False,
    dry_run: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ExportStats:
    """Run full DJ export: curate → (key detect) → transcode → place.

    Args:
        tracks: TrackRow list (from XLSX or DB)
        config: DJ curation configuration
        output_root: Destination root (e.g. /Volumes/MUSIC/DJ_YES)
        jobs: Parallel transcode workers
        overwrite: Overwrite existing output files
        detect_keys: Run KeyFinder on passed tracks before transcoding
        dry_run: Plan only, no transcoding
        progress_callback: Called with (completed, total) after each transcode

    Returns:
        ExportStats with counts for each stage
    """
    _ = output_root
    candidates = [
        {
            "artist": t.track_artist or t.album_artist,
            "duration_sec": None,
            "genre": None,
            "_track": t,
        }
        for t in tracks
    ]
    curation = filter_candidates(candidates, config)
    passed_tracks = [c["_track"] for c in curation.passed]

    stats = ExportStats(
        total_candidates=len(tracks),
        passed_curation=len(curation.passed),
        rejected_curation=len(curation.rejected_blocklist)
        + len(curation.rejected_duration)
        + len(curation.rejected_genre),
    )

    log.info(
        "Curation complete: %d passed, %d rejected, %d flagged for review",
        stats.passed_curation,
        stats.rejected_curation,
        len(curation.flagged_reviewlist),
    )

    if dry_run:
        log.info("Dry run — skipping key detection and transcoding")
        return stats

    if detect_keys and is_keyfinder_available():
        log.info("Detecting keys for %d tracks...", len(passed_tracks))
        for track in passed_tracks:
            key = detect_key(track.source_path)
            if key:
                stats.keys_detected += 1
            else:
                stats.keys_skipped += 1
    else:
        stats.keys_skipped = len(passed_tracks)

    total = len(passed_tracks)
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [pool.submit(transcode_one, track, overwrite) for track in passed_tracks]
        for future in as_completed(futures):
            status, track, error = future.result()
            completed += 1
            if status == "ok":
                stats.transcoded_ok += 1
            elif status == "skipped_existing":
                stats.transcoded_skipped += 1
            else:
                stats.transcoded_failed += 1
                log.warning("Transcode failed for %s: %s", track.source_path, error)
            if progress_callback:
                progress_callback(completed, total)

    log.info(
        "Export complete: %d ok, %d skipped, %d failed",
        stats.transcoded_ok,
        stats.transcoded_skipped,
        stats.transcoded_failed,
    )
    return stats
