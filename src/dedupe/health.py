"""Health check utilities for audio files.

This module centralises the logic for probing file integrity so that different
commands can share consistent behaviour.  All health checkers follow the
:class:`HealthChecker` protocol which returns ``(healthy, note)`` tuples where
``healthy`` indicates pass/fail/unknown and ``note`` provides diagnostic
context.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Tuple

HealthStatus = Tuple[Optional[bool], Optional[str]]


class HealthChecker(Protocol):
    """Protocol describing objects that can evaluate file health."""

    def check(self, path: Path) -> HealthStatus:
        """Return ``(healthy, note)`` for *path*."""


@dataclass
class CommandPaths:
    """Paths to external binaries used for health checks."""

    flac: Optional[str]
    ffmpeg: Optional[str]


class NullHealthChecker:
    """Health checker that always reports unknown health."""

    def check(self, path: Path) -> HealthStatus:
        return None, "health check disabled"


class CommandHealthChecker:
    """Health checker that shells out to ``flac`` or ``ffmpeg``.

    The checker prefers ``flac -t`` for FLAC files because it performs a
    format-aware integrity check.  When ``flac`` is unavailable it falls back
    to streaming the file through ``ffmpeg`` with ``-f null -``.
    """

    def __init__(self, timeout: int = 45) -> None:
        self.timeout = timeout
        self.paths = CommandPaths(
            flac=shutil.which("flac"),
            ffmpeg=shutil.which("ffmpeg"),
        )

    def check(self, path: Path) -> HealthStatus:
        if not path.exists():
            return None, "file missing"

        ext = path.suffix.lower()
        if ext == ".flac" and self.paths.flac:
            return self._run_flac(path)
        if self.paths.ffmpeg:
            return self._run_ffmpeg(path)
        return None, "no health tools available"

    def _run_flac(self, path: Path) -> HealthStatus:
        assert self.paths.flac is not None
        try:
            result = subprocess.run(
                [self.paths.flac, "-t", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return False, "flac -t timed out"
        except OSError as exc:
            return None, f"flac unavailable: {exc}"

        if result.returncode == 0:
            return True, "flac -t"
        note = result.stderr.strip() or result.stdout.strip() or "flac -t failed"
        return False, note

    def _run_ffmpeg(self, path: Path) -> HealthStatus:
        assert self.paths.ffmpeg is not None
        try:
            result = subprocess.run(
                [
                    self.paths.ffmpeg,
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


__all__ = [
    "CommandHealthChecker",
    "HealthChecker",
    "HealthStatus",
    "NullHealthChecker",
]
