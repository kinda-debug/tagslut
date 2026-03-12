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
from tagslut.dj.transcode import TrackRow, build_output_path, sanitize_component, transcode_one
from tagslut.storage.models import DJ_SET_ROLES, DJ_SET_ROLE_ORDER

logger = logging.getLogger(__name__)
log = logger
_ROLE_PLAYLIST_FILENAMES = {
    role: f"{index * 10}_{role.upper()}.m3u"
    for index, role in enumerate(DJ_SET_ROLE_ORDER, start=1)
}


@dataclass
class PoolProfile:
    pool_name: str = ""
    layout: str = "flat"
    filename_template: str = "{artist} - {title}.mp3"
    bpm_min: int | None = None
    bpm_max: int | None = None
    only_roles: list[str] | None = None
    create_playlist: bool = False
    pool_overwrite_policy: str = "always"


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
    profile: PoolProfile | None = None


def pool_profile_from_dict(d: dict) -> PoolProfile:
    """Construct PoolProfile from a profile JSON dict."""
    if not isinstance(d, dict):
        raise TypeError("Pool profile must be a dict.")

    layout = str(d.get("layout") or "flat").strip().lower() or "flat"
    if layout not in {"flat", "by_role"}:
        raise ValueError("Pool profile layout must be 'flat' or 'by_role'.")

    pool_overwrite_policy = str(d.get("pool_overwrite_policy") or "always").strip().lower() or "always"
    if pool_overwrite_policy not in {"always", "skip"}:
        raise ValueError("Pool profile overwrite policy must be 'always' or 'skip'.")

    raw_only_roles = d.get("only_roles")
    only_roles: list[str] | None = None
    if raw_only_roles is not None:
        if isinstance(raw_only_roles, str) or not isinstance(raw_only_roles, (list, tuple, set, frozenset)):
            raise ValueError(f"only_roles must be a list of DJ set roles: {sorted(DJ_SET_ROLES)}")
        only_roles = []
        for value in raw_only_roles:
            role = _normalize_dj_set_role(value)
            if role is None:
                raise ValueError(f"Invalid only_roles value {value!r}. Allowed: {sorted(DJ_SET_ROLES)}")
            if role not in only_roles:
                only_roles.append(role)

    return PoolProfile(
        pool_name=str(d.get("pool_name") or ""),
        layout=layout,
        filename_template=str(d.get("filename_template") or "{artist} - {title}.mp3"),
        bpm_min=int(d["bpm_min"]) if d.get("bpm_min") is not None else None,
        bpm_max=int(d["bpm_max"]) if d.get("bpm_max") is not None else None,
        only_roles=only_roles,
        create_playlist=bool(d.get("create_playlist", False)),
        pool_overwrite_policy=pool_overwrite_policy,
    )


def _normalize_dj_set_role(value: object) -> str | None:
    role = str(value or "").strip().lower()
    if not role or role not in DJ_SET_ROLES:
        return None
    return role


def _fallback_filename(track: TrackRow, output_root: Path) -> str:
    if track.output_path is not None:
        return track.output_path.name
    return build_output_path(output_root, track).name


def _render_profile_filename(track: TrackRow, output_root: Path, profile: PoolProfile) -> str:
    fallback_name = _fallback_filename(track, output_root)
    artist = track.track_artist or track.album_artist or track.source_path.stem
    title = track.title or track.source_path.stem
    try:
        rendered = str(profile.filename_template).format_map({"artist": artist, "title": title}).strip()
    except Exception as exc:
        log.warning("Failed to render filename template for %s: %s", track.source_path, exc)
        return fallback_name

    if not rendered:
        return fallback_name

    candidate = sanitize_component(Path(rendered).name, fallback_name)
    if "." not in candidate:
        suffix = Path(fallback_name).suffix or ".mp3"
        candidate = f"{candidate}{suffix}"
    return candidate


def _resolve_output_path(
    track: TrackRow,
    output_root: Path,
    profile: PoolProfile,
) -> Path:
    """
    Resolve the destination path for a track under the supplied pool profile.
    """
    base_root = output_root
    if profile.layout == "by_role":
        role = _normalize_dj_set_role(track.dj_set_role)
        if role is None:
            log.warning(
                "Track %s has invalid or missing dj_set_role %r; routing to _unassigned",
                track.source_path,
                track.dj_set_role,
            )
            base_root = output_root / "_unassigned"
        else:
            base_root = output_root / role
    elif profile.layout != "flat":
        raise ValueError(f"Unsupported pool layout {profile.layout!r}")

    return base_root / _render_profile_filename(track, output_root, profile)


def _apply_profile_output_paths(
    tracks: list[TrackRow],
    output_root: Path,
    profile: PoolProfile,
) -> None:
    used_paths: dict[Path, int] = {}
    for track in tracks:
        proposed = _resolve_output_path(track, output_root, profile)
        count = used_paths.get(proposed, 0)
        if count > 0:
            proposed = proposed.with_name(f"{proposed.stem}__{count + 1}{proposed.suffix}")
        used_paths[proposed] = count + 1
        track.output_path = proposed


def _apply_profile_role_filter(tracks: list[TrackRow], profile: PoolProfile | None) -> list[TrackRow]:
    if profile is None or profile.only_roles is None:
        return tracks

    allowed_roles = set(profile.only_roles)
    filtered = [track for track in tracks if _normalize_dj_set_role(track.dj_set_role) in allowed_roles]
    excluded = len(tracks) - len(filtered)
    if excluded:
        log.info("Excluded %d track(s) via profile.only_roles filter", excluded)
    return filtered


def _write_role_playlists(
    output_root: Path,
    tracks_by_role: dict[str, list[Path]],
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    for role in DJ_SET_ROLE_ORDER:
        playlist_path = output_root / _ROLE_PLAYLIST_FILENAMES[role]
        lines = [
            str(path.relative_to(output_root))
            for path in sorted(tracks_by_role.get(role, []))
        ]
        playlist_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def plan_export(
    tracks: list[TrackRow],
    config: DjCurationConfig,
    output_root: Path,
    *,
    profile: PoolProfile | None = None,
) -> ExportPlan:
    """Dry-run: apply curation filters and build export plan without transcoding."""
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
    passed_tracks = _apply_profile_role_filter(passed_tracks, profile)
    if profile is not None:
        _apply_profile_output_paths(passed_tracks, output_root, profile)

    return ExportPlan(
        tracks=passed_tracks,
        curation_result=curation,
        stats=stats,
        dry_run=True,
        profile=profile,
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
    profile: PoolProfile | None = None,
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
    passed_tracks = _apply_profile_role_filter(passed_tracks, profile)
    if profile is not None:
        _apply_profile_output_paths(passed_tracks, output_root, profile)

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
    successful_role_paths: dict[str, list[Path]] = {role: [] for role in DJ_SET_ROLE_ORDER}

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
                if profile is not None and profile.layout == "by_role":
                    role = _normalize_dj_set_role(track.dj_set_role)
                    if role in successful_role_paths and track.output_path is not None:
                        successful_role_paths[role].append(track.output_path)
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
    if profile is not None and profile.create_playlist and profile.layout == "by_role":
        _write_role_playlists(output_root, successful_role_paths)

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
