"""Synchronize duplicate staging directory with the main music library.

This module reads the staged duplicate directory listing from
``DEDUPE_DIR.txt`` and walks the corresponding filesystem tree. Every audio
file under the dedupe directory is compared with the matching path in the
main library. The healthiest copy is kept in the library and the duplicate is
deleted once the preferred file is in place.

The implementation is intentionally conservative: operations happen one file
at a time, each move/delete is wrapped in small helper functions, and the
health check logic is pluggable so unit tests can inject deterministic
behaviour.  The default checker relies on the ``flac`` or ``ffmpeg`` command
line tools when available, but gracefully degrades to "unknown health" when
neither tool exists on the system running the script.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Protocol, Sequence, Tuple


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


class HealthChecker(Protocol):
    """Protocol describing objects that can evaluate file health."""

    def check(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        """Return ``(healthy, note)`` for *path*.

        ``healthy`` is ``True`` when the file passes the health check,
        ``False`` when the check fails, or ``None`` if the checker cannot
        determine health.  ``note`` provides diagnostic context for logging
        and reporting.
        """


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


class NullHealthChecker:
    """Health checker that always reports unknown health.

    Useful for dry-run scenarios or unit tests that focus on file movement
    semantics without invoking external tools.
    """

    def check(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        """Return ``(None, note)`` to signal that health is unknown."""

        return None, "health check disabled"


class CommandHealthChecker:
    """Health checker that shells out to ``flac`` or ``ffmpeg``.

    The checker prefers ``flac -t`` for FLAC files because it performs a
    format-aware integrity check. When ``flac`` is unavailable, it falls back
    to streaming the file through ``ffmpeg`` with ``-f null -``. Any failure
    (non-zero exit code, timeout, or unexpected exception) marks the file as
    unhealthy so the caller can favour an alternative copy.
    """

    def __init__(self, timeout: int = 45) -> None:
        self.timeout = timeout
        self.flac_path = shutil.which("flac")
        self.ffmpeg_path = shutil.which("ffmpeg")

    def check(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        if not path.exists():
            return None, "file missing"

        ext = path.suffix.lower()
        if ext == ".flac" and self.flac_path:
            return self._run_flac(path)
        if self.ffmpeg_path:
            return self._run_ffmpeg(path)
        return None, "no health tools available"

    def _run_flac(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        """Execute ``flac -t`` and translate the result into a health tuple."""
        assert self.flac_path is not None
        try:
            result = subprocess.run(
                [self.flac_path, "-t", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "flac -t timed out"
        except OSError as exc:  # tool vanished mid-run or permissions issue
            return None, f"flac unavailable: {exc}"

        if result.returncode == 0:
            return True, "flac -t"
        note = result.stderr.strip() or result.stdout.strip() or "flac -t failed"
        return False, note

    def _run_ffmpeg(self, path: Path) -> Tuple[Optional[bool], Optional[str]]:
        """Execute an ``ffmpeg`` decode and return the resulting health tuple."""
        assert self.ffmpeg_path is not None
        try:
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:a",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "ffmpeg decode timed out"
        except OSError as exc:
            return None, f"ffmpeg unavailable: {exc}"

        if result.returncode == 0:
            return True, "ffmpeg decode"
        note = result.stderr.strip() or result.stdout.strip() or "ffmpeg decode failed"
        return False, note


def discover_dedupe_root(listing_path: Path) -> Path:
    """Extract the dedupe directory path from ``DEDUPE_DIR.txt``.

    The listing file is generated from a shell session where ``tree`` was run
    against the dedupe directory. The path we need appears before the ``>``
    prompt marker. This helper uses a regular expression to capture the first
    absolute path that matches that pattern.
    """

    text = listing_path.read_text(encoding="utf-8")
    match = re.search(r"^(\/[^>]+?)\s*>", text, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to discover dedupe directory from {listing_path}")
    return Path(match.group(1).strip())


def parse_library_root(config_path: Path) -> Path:
    """Return library root from ``config.toml`` when available."""

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


def iter_audio_files(root: Path) -> Iterable[Path]:
    """Yield every audio file under *root* as a relative path."""

    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTS:
            yield path.relative_to(root)


def gather_track_info(path: Path, checker: HealthChecker) -> TrackInfo:
    """Collect metadata and health information for *path*."""
    try:
        st: os.stat_result = path.stat()
    except FileNotFoundError:
        return TrackInfo(path=path, exists=False, healthy=None, health_note="file missing", size=0, mtime_ns=0)

    healthy: Optional[bool]
    note: Optional[str]
    healthy, note = checker.check(path)
    size = int(st.st_size)
    mtime_ns = int(st.st_mtime_ns)
    return TrackInfo(path=path, exists=True, healthy=healthy, health_note=note, size=size, mtime_ns=mtime_ns)


def _health_score(info: TrackInfo) -> int:
    """Return an integer ranking for the track's health state."""
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
    """Create the parent directory for *path* when it does not exist."""

    path.parent.mkdir(parents=True, exist_ok=True)


def prune_empty_parents(relative_path: Path, dedupe_root: Path) -> None:
    """Remove empty parent directories under ``dedupe_root`` for *relative_path*."""

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
            return SyncOutcome(relative_path, "would-move", "library missing; move staged copy")

        ensure_parent_directory(library_path)
        dedupe_path.rename(library_path)
        prune_empty_parents(relative_path, dedupe_root)
        return SyncOutcome(relative_path, "moved", "dedupe copy installed into library")

    preferred = pick_preferred_track(library_info, dedupe_info)
    if preferred == "library":
        if dry_run:
            return SyncOutcome(relative_path, "would-delete", "library already healthiest; delete staged duplicate")

        dedupe_path.unlink()
        prune_empty_parents(relative_path, dedupe_root)
        return SyncOutcome(relative_path, "deleted", "removed duplicate from staging")

    if dry_run:
        return SyncOutcome(relative_path, "would-swap", "staged copy healthier; swap into library")

    temp_path = library_path.with_suffix(library_path.suffix + ".swap")
    library_path.rename(temp_path)
    try:
        dedupe_path.rename(library_path)
    except Exception:
        temp_path.rename(library_path)
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


def build_argument_parser() -> argparse.ArgumentParser:
    """Return an ``ArgumentParser`` for the CLI entry point."""

    parser = argparse.ArgumentParser(
        description="Ensure the healthiest copy of each staged track lives in the main library",
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=parse_library_root(Path("config.toml")),
        help="Root directory of the main music library",
    )
    parser.add_argument(
        "--dedupe-root",
        type=Path,
        default=None,
        help="Override dedupe directory (defaults to path discovered via DEDUPE_DIR.txt)",
    )
    parser.add_argument(
        "--dedupe-listing",
        type=Path,
        default=DEFAULT_DEDUPE_LISTING,
        help="Path to DEDUPE_DIR.txt listing file used to discover dedupe directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without modifying any files",
    )
    parser.add_argument(
        "--health-check",
        choices=("auto", "none"),
        default="auto",
        help="Enable automatic health checks (default) or disable them",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Health check timeout in seconds for external commands",
    )
    return parser


def run_cli(args: Sequence[str] | None = None) -> int:
    """Entry point used by ``main`` and unit tests."""

    parser = build_argument_parser()
    ns = parser.parse_args(args=args)

    dedupe_root = ns.dedupe_root or discover_dedupe_root(ns.dedupe_listing)
    if not dedupe_root.exists():
        parser.error(f"Dedupe directory {dedupe_root} does not exist")

    checker: HealthChecker
    if ns.health_check == "auto":
        checker = CommandHealthChecker(timeout=ns.timeout)
    else:
        checker = NullHealthChecker()

    outcomes = synchronise_directory(ns.library_root, dedupe_root, checker, dry_run=ns.dry_run)

    counts: Dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.action] = counts.get(outcome.action, 0) + 1
        print(f"{outcome.action:>12}  {outcome.relative_path}  {outcome.message}")

    summary = ", ".join(f"{action}: {count}" for action, count in sorted(counts.items()))
    print(f"Processed {len(outcomes)} files — {summary if summary else 'no actions performed'}")
    return 0


def main() -> int:
    """Console script entry point."""

    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
