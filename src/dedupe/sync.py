"""Synchronise staged duplicates with the main library."""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from .health import CommandHealthChecker, HealthChecker, NullHealthChecker

AUDIO_EXTS = {
    ".flac",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".aif",
    ".aiff",
    ".aifc",
    ".ogg",
    ".opus",
    ".wma",
    ".mka",
    ".mkv",
    ".alac",
}

DEFAULT_LIBRARY_ROOT = Path("/Volumes/dotad/MUSIC")
DEFAULT_DEDUPE_LISTING = Path("DEDUPE_DIR.txt")


class HealthMode(str, Enum):
    """How health checks should be performed during synchronisation."""

    AUTO = "auto"
    NONE = "none"


@dataclass
class TrackInfo:
    """Metadata describing a single track in the library or dedupe tree."""

    path: Path
    exists: bool
    healthy: Optional[bool]
    health_note: Optional[str]
    size: int
    mtime_ns: int


@dataclass
class SyncOutcome:
    """Result for synchronising a single track relative path."""

    relative_path: Path
    action: str
    message: str


@dataclass
class LibraryHealthResult:
    """Playback verification outcome for a single library track."""

    relative_path: Path
    exists: bool
    healthy: Optional[bool]
    note: Optional[str]


@dataclass
class SyncSummary:
    """Summary data returned by :func:`run_sync`."""

    outcomes: List[SyncOutcome]
    counts: Counter[str]
    audit_results: Optional[List[LibraryHealthResult]] = None


def discover_dedupe_root(listing_path: Path) -> Path:
    """Extract the dedupe directory path from ``DEDUPE_DIR.txt``."""

    text = listing_path.read_text(encoding="utf-8")
    match = re.search(r"^(\/[^>]+?)\s*>", text, re.MULTILINE)
    if not match:
        raise ValueError(
            f"Could not discover dedupe directory from {listing_path}"  # pragma: no cover
        )
    return Path(match.group(1))


def parse_library_root(config_path: Path) -> Path:
    """Extract the library root from ``config.toml`` when available."""

    if not config_path.exists():
        return DEFAULT_LIBRARY_ROOT
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_LIBRARY_ROOT

    match = re.search(r"^root\s*=\s*\"([^\"]+)\"", text, re.MULTILINE)
    if match:
        return Path(match.group(1))
    return DEFAULT_LIBRARY_ROOT


def iter_audio_files(root: Path) -> Iterator[Path]:
    """Yield every audio file under *root* as a relative path."""

    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTS:
            yield path.relative_to(root)


def gather_track_info(path: Path, checker: HealthChecker) -> TrackInfo:
    """Collect metadata and health information for *path*."""

    try:
        st: os.stat_result = path.stat()
    except FileNotFoundError:
        return TrackInfo(
            path=path,
            exists=False,
            healthy=None,
            health_note="file missing",
            size=0,
            mtime_ns=0,
        )

    healthy: Optional[bool]
    note: Optional[str]
    healthy, note = checker.check(path)
    size = int(st.st_size)
    mtime_ns = int(st.st_mtime_ns)
    return TrackInfo(
        path=path,
        exists=True,
        healthy=healthy,
        health_note=note,
        size=size,
        mtime_ns=mtime_ns,
    )


def _health_score(info: TrackInfo) -> int:
    if not info.exists:
        return -1
    if info.healthy is True:
        return 2
    if info.healthy is None:
        return 1
    return 0


def pick_preferred_track(library: TrackInfo, dedupe: TrackInfo) -> str:
    """Return ``"library"`` or ``"dedupe"`` for the preferred track."""

    lib_score = _health_score(library)
    dd_score = _health_score(dedupe)
    if lib_score != dd_score:
        return "library" if lib_score > dd_score else "dedupe"

    if library.size != dedupe.size:
        return "library" if library.size >= dedupe.size else "dedupe"

    if library.mtime_ns != dedupe.mtime_ns:
        return "library" if library.mtime_ns >= dedupe.mtime_ns else "dedupe"

    return "library"


def ensure_parent_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def prune_empty_parents(relative_path: Path, dedupe_root: Path) -> None:
    staged_path = dedupe_root / relative_path
    for parent in staged_path.parents:
        if parent == dedupe_root:
            break
        try:
            parent.rmdir()
        except OSError:
            break


def synchronize_track(
    relative_path: Path,
    library_root: Path,
    dedupe_root: Path,
    checker: HealthChecker,
    *,
    dry_run: bool = False,
) -> SyncOutcome:
    """Synchronise a single track and return the performed action."""

    library_path = library_root / relative_path
    dedupe_path = dedupe_root / relative_path

    dedupe_info = gather_track_info(dedupe_path, checker)
    if not dedupe_info.exists:
        return SyncOutcome(relative_path, "skip", "dedupe file missing")

    library_info = gather_track_info(library_path, checker)

    if not library_info.exists:
        if dry_run:
            return SyncOutcome(
                relative_path, "would-move", "library missing; move staged copy"
            )

        ensure_parent_directory(library_path)
        dedupe_path.rename(library_path)
        prune_empty_parents(relative_path, dedupe_root)
        return SyncOutcome(relative_path, "moved", "dedupe copy installed into library")

    preferred = pick_preferred_track(library_info, dedupe_info)
    if preferred == "library":
        if dry_run:
            return SyncOutcome(
                relative_path,
                "would-delete",
                "library already healthiest; delete staged duplicate",
            )

        dedupe_path.unlink()
        prune_empty_parents(relative_path, dedupe_root)
        return SyncOutcome(relative_path, "deleted", "removed duplicate from staging")

    if dry_run:
        return SyncOutcome(
            relative_path, "would-swap", "staged copy healthier; swap into library"
        )

    temp_path = library_path.with_suffix(library_path.suffix + ".swap")
    library_path.rename(temp_path)
    try:
        dedupe_path.rename(library_path)
    except OSError:
        try:
            temp_path.rename(library_path)
        except OSError:
            pass
        raise

    temp_path.unlink()
    prune_empty_parents(relative_path, dedupe_root)
    return SyncOutcome(relative_path, "swapped", "staged copy replaced library version")


def synchronise_directory(
    library_root: Path,
    dedupe_root: Path,
    checker: HealthChecker,
    *,
    dry_run: bool = False,
) -> List[SyncOutcome]:
    """Process every audio file under *dedupe_root* and return outcomes."""

    outcomes: List[SyncOutcome] = []
    for relative_path in iter_audio_files(dedupe_root):
        outcomes.append(
            synchronize_track(
                relative_path,
                library_root,
                dedupe_root,
                checker,
                dry_run=dry_run,
            )
        )
    return outcomes


def audit_library_playback(
    library_root: Path, checker: HealthChecker
) -> List[LibraryHealthResult]:
    """Decode every audio track in *library_root* to verify uninterrupted playback."""

    results: List[LibraryHealthResult] = []
    for relative_path in iter_audio_files(library_root):
        absolute_path = library_root / relative_path
        info = gather_track_info(absolute_path, checker)
        results.append(
            LibraryHealthResult(
                relative_path=relative_path,
                exists=info.exists,
                healthy=info.healthy,
                note=info.health_note,
            )
        )
    return results


def _build_checker(mode: HealthMode, timeout: int) -> HealthChecker:
    if mode is HealthMode.AUTO:
        return CommandHealthChecker(timeout=timeout)
    return NullHealthChecker()


def run_sync(
    *,
    library_root: Path,
    dedupe_root: Optional[Path] = None,
    dedupe_listing: Path = DEFAULT_DEDUPE_LISTING,
    health_mode: HealthMode = HealthMode.AUTO,
    timeout: int = 45,
    dry_run: bool = False,
    verify_library: bool = False,
) -> SyncSummary:
    """Run the synchronisation workflow and return a :class:`SyncSummary`."""

    resolved_dedupe = dedupe_root or discover_dedupe_root(dedupe_listing)
    if not resolved_dedupe.exists():
        raise FileNotFoundError(f"Dedupe directory {resolved_dedupe} does not exist")

    checker = _build_checker(health_mode, timeout)
    outcomes = synchronise_directory(
        library_root, resolved_dedupe, checker, dry_run=dry_run
    )

    counts: Counter[str] = Counter(outcome.action for outcome in outcomes)
    audit_results: Optional[List[LibraryHealthResult]] = None

    if verify_library:
        if health_mode is HealthMode.NONE:
            raise ValueError("Library verification requires active health checks")
        audit_results = audit_library_playback(library_root, checker)

    return SyncSummary(outcomes=outcomes, counts=counts, audit_results=audit_results)



def run_cli(args: Sequence[str] | None = None) -> int:
    """Compatibility CLI that preserves the legacy argument contract."""

    from scripts.dedupe_sync import run_cli as _legacy_run_cli

    return _legacy_run_cli(args)

__all__ = [
    "AUDIO_EXTS",
    "DEFAULT_DEDUPE_LISTING",
    "DEFAULT_LIBRARY_ROOT",
    "HealthMode",
    "LibraryHealthResult",
    "SyncOutcome",
    "SyncSummary",
    "audit_library_playback",
    "discover_dedupe_root",
    "gather_track_info",
    "iter_audio_files",
    "parse_library_root",
    "pick_preferred_track",
    "run_cli",
    "run_sync",
    "synchronise_directory",
    "synchronize_track",
]
