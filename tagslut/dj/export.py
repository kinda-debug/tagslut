from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
from pathlib import Path
import subprocess
import sys
from typing import Callable

from tagslut.dj.curation import CurationResult, DjCurationConfig, filter_candidates
from tagslut.dj.key_detection import detect_key, is_keyfinder_available
from tagslut.dj.transcode import TrackRow, transcode_one

logger = logging.getLogger(__name__)
log = logger


@dataclass
class ExportStats:
    total_candidates: int = 0
    passed_curation: int = 0
    rejected_curation: int = 0
    transcoded_ok: int = 0
    transcoded_skipped: int = 0
    transcoded_failed: int = 0
    missing_source: int = 0
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
    candidates = _build_candidates(tracks, allow_duration_estimation=False)

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
    safe_mode: bool = False,
    transcode_timeout_s: int | None = None,
    fail_fast: bool = False,
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
    if safe_mode:
        print("Loading track overrides...", flush=True)
    print("Building candidates...", flush=True)
    allow_duration_estimation = (not safe_mode) and (not dry_run)
    candidates = _build_candidates(
        tracks,
        allow_duration_estimation=allow_duration_estimation,
    )
    print("Running curation filters...", flush=True)
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

    missing_tracks: list[TrackRow] = []
    for track in passed_tracks:
        if not track.source_path.exists():
            stats.missing_source += 1
            missing_tracks.append(track)

    if missing_tracks:
        manifest_rows = [
            {
                "path": str(track.output_path or track.source_path),
                "artist": track.track_artist or track.album_artist,
                "title": track.title,
                "key": track.canonical_key,
                "transcode_status": "missing",
                "source_path": str(track.source_path),
                "error": "missing_source",
            }
            for track in missing_tracks
        ]
    else:
        manifest_rows = []
    failure_rows: list[dict[str, str | None]] = []
    if missing_tracks:
        for track in missing_tracks:
            failure_rows.append(
                {
                    "path": str(track.source_path),
                    "output_path": str(track.output_path or ""),
                    "status": "missing_source",
                    "error": "missing_source",
                }
            )
    if missing_tracks:
        missing_ids = {id(t) for t in missing_tracks}
        passed_tracks = [t for t in passed_tracks if id(t) not in missing_ids]

    if dry_run:
        print("Dry run complete.", flush=True)
        log.info("Dry run — skipping key detection and transcoding")
        return stats

    print("Starting transcode...", flush=True)
    if detect_keys and is_keyfinder_available():
        log.info("Detecting keys for %d tracks...", len(passed_tracks))
        for track in passed_tracks:
            key = detect_key(track.source_path)
            if key:
                track.canonical_key = key
                stats.keys_detected += 1
            else:
                stats.keys_skipped += 1
    else:
        stats.keys_skipped = len(passed_tracks)

    total = len(passed_tracks)
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = [
            pool.submit(transcode_one, track, overwrite, transcode_timeout_s)
            for track in passed_tracks
        ]
        for future in as_completed(futures):
            status, track, error, stderr = future.result()
            completed += 1
            if status == "ok":
                stats.transcoded_ok += 1
            elif status == "skipped_existing":
                stats.transcoded_skipped += 1
            else:
                stats.transcoded_failed += 1
                log.warning("Transcode failed for %s: %s", track.source_path, error)
                failure_rows.append(
                    {
                        "path": str(track.source_path),
                        "output_path": str(track.output_path or ""),
                        "status": status,
                        "error": error,
                        "stderr": (stderr or "")[:2000],
                    }
                )
                if fail_fast:
                    for pending in futures:
                        pending.cancel()
                    break
            if progress_callback:
                progress_callback(completed, total)

            manifest_rows.append(
                {
                    "path": str(track.output_path or track.source_path),
                    "artist": track.track_artist or track.album_artist,
                    "title": track.title,
                    "key": track.canonical_key,
                    "transcode_status": status,
                    "error": error if status not in {"ok", "skipped_existing"} else "",
                }
            )

    if manifest_rows:
        manifest_path = output_root / "export_manifest.jsonl"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        for_write = sorted(manifest_rows, key=lambda row: str(row.get("path") or ""))
        with manifest_path.open("w", encoding="utf-8") as handle:
            for row in for_write:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    if failure_rows:
        failure_path = output_root / "export_failures.jsonl"
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        for_write = sorted(failure_rows, key=lambda row: str(row.get("path") or ""))
        with failure_path.open("w", encoding="utf-8") as handle:
            for row in for_write:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    log.info(
        "Export complete: %d ok, %d skipped, %d failed",
        stats.transcoded_ok,
        stats.transcoded_skipped,
        stats.transcoded_failed,
    )
    return stats


def get_audio_duration(path: Path, timeout_sec: int = 8) -> float | None:
    """Return audio duration in seconds, or None if unavailable."""
    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception as e:
        logger.debug("mutagen import unavailable while probing duration for %s: %s", path, e)
        MutagenFile = None

    if MutagenFile is not None:
        try:
            audio = MutagenFile(path)
        except Exception as e:
            logger.debug("mutagen failed while probing duration for %s: %s", path, e)
            audio = None
        if audio is not None and hasattr(audio, "info") and hasattr(audio.info, "length"):
            try:
                duration = float(audio.info.length)
                if duration > 0:
                    return duration
            except Exception as e:
                logger.debug("Failed to parse audio duration for %s: %s", path, e)
                pass

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _build_candidates(
    tracks: list[TrackRow],
    *,
    allow_duration_estimation: bool,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    estimate_total = sum(
        1
        for track in tracks
        if allow_duration_estimation and not getattr(track, "duration_sec", None)
    )
    if estimate_total:
        print(
            f"Estimating durations for {estimate_total} tracks (this may take a moment)...",
            end="",
            flush=True,
        )
    estimated = 0
    for track in tracks:
        duration = getattr(track, "duration_sec", None)
        if allow_duration_estimation and not duration:
            duration = get_audio_duration(track.source_path)
            estimated += 1
            if estimate_total and estimated % 10 == 0:
                sys.stdout.write(".")
                sys.stdout.flush()
        candidates.append(
            {
                "artist": track.track_artist or track.album_artist,
                "title": track.title,
                "path": str(track.source_path),
                "duration_sec": duration,
                "genre": None,
                "_track": track,
            }
        )
    if estimate_total:
        print("", flush=True)
    return candidates
