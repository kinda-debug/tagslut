"""Health scoring utilities for FLAC files."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:
    from mutagen.flac import FLAC
except ImportError:  # pragma: no cover - optional dependency
    FLAC = None  # type: ignore

LOGGER = logging.getLogger(__name__)

REQUIRED_TAGS = ("artist", "album", "title", "date")
TRACK_TAG_CANDIDATES = ("tracknumber", "track")


@dataclass(slots=True)
class HealthResult:
    """Structured summary of a file's health evaluation."""

    path: Path
    score: int
    reasons: list[str]
    tags_ok: bool
    audio_ok: bool


def _run_flac_test(path: Path) -> bool:
    """Return ``True`` when ``flac --test`` reports a healthy file."""

    try:
        result = subprocess.run(
            ["flac", "--test", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _normalise_tags(tags: Mapping[str, Any] | None) -> Mapping[str, Any]:
    """Return lowercase tag keys for consistent lookup."""

    return {key.lower(): value for key, value in (tags or {}).items()}


def _evaluate_tags(tags: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Assess whether the tag set contains the required metadata."""

    reasons: list[str] = []
    missing = [tag for tag in REQUIRED_TAGS if tag not in tags]
    if not any(tag in tags for tag in TRACK_TAG_CANDIDATES):
        missing.append("tracknumber")
    if missing:
        reasons.append(f"Missing required tags: {', '.join(sorted(set(missing)))}")
    return not missing, reasons


def evaluate_flac(path: Path) -> HealthResult:
    """Evaluate the technical and tagging quality of a FLAC file.

    The returned :class:`HealthResult` includes a 0–10 score, a list of
    human-readable reasons for deductions, and boolean flags describing tag
    completeness and audio integrity. Scores start at 10 and subtract points
    for validation failures: 6 for an invalid stream, 2 for missing duration,
    1 when mutagen reports no MD5 signature, and 2 for missing required tags.
    """

    reasons: list[str] = []
    path = Path(path)

    if not path.is_file():
        reasons.append("File does not exist or is not a regular file.")
        return HealthResult(path=path, score=0, reasons=reasons, tags_ok=False, audio_ok=False)

    audio = None
    duration_ok = False
    audio_md5_ok = False

    if FLAC is None:
        reasons.append("mutagen is not available; tag analysis limited.")
    else:
        try:
            audio = FLAC(path)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug("mutagen failed for %s: %s", path, exc)
            reasons.append("Unable to parse FLAC metadata with mutagen.")
        else:
            duration_ok = bool(getattr(audio.info, "length", 0) and audio.info.length > 0)
            audio_md5_ok = bool(getattr(audio.info, "md5_signature", None))

    tags = _normalise_tags(getattr(audio, "tags", None))
    if FLAC is None:
        tags_ok, tag_reasons = False, ["Tags unavailable because mutagen is not installed."]
    elif tags:
        tags_ok, tag_reasons = _evaluate_tags(tags)
    else:
        tags_ok, tag_reasons = False, ["No tags present."]
    reasons.extend(tag_reasons)

    audio_valid = duration_ok
    if not audio_valid:
        audio_valid = _run_flac_test(path)
        if not audio_valid:
            reasons.append("FLAC stream failed validation.")
    if not duration_ok:
        reasons.append("Duration missing or zero.")
    if FLAC is not None and not audio_md5_ok:
        reasons.append("Audio MD5 signature missing.")

    score = 10
    if not audio_valid:
        score -= 6
    if not duration_ok:
        score -= 2
    if FLAC is not None and not audio_md5_ok:
        score -= 1
    if not tags_ok:
        score -= 2
    score = max(0, min(10, score))

    return HealthResult(
        path=path,
        score=score,
        reasons=reasons,
        tags_ok=tags_ok,
        audio_ok=audio_valid,
    )

