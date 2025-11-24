"""File health scoring utilities."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict

try:
    from mutagen.flac import FLAC
except ImportError:  # pragma: no cover - optional dependency
    FLAC = None  # type: ignore

LOGGER = logging.getLogger(__name__)


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


def score_file(path: Path) -> Dict[str, object]:
    """Score a FLAC file and return a detailed assessment.

    The score ranges from 0 (unusable) to 10 (perfect). Container validity,
    audio checksum integrity, required tags, and duration are all considered.
    """

    path = Path(path)
    is_valid_flac = False
    audio_md5_ok = False
    tags_ok = False
    duration_ok = False

    if FLAC is not None:
        try:
            audio = FLAC(path)
            is_valid_flac = True
            duration_ok = bool(audio.info.length and audio.info.length > 0)
            audio_md5_ok = bool(audio.info.md5_signature)
            tags = {k.lower(): v for k, v in (audio.tags or {}).items()}
            tags_ok = all(
                key in tags
                for key in (
                    "artist",
                    "album",
                    "title",
                    "tracknumber",
                    "date",
                )
            ) or (
                all(key in tags for key in ("artist", "album", "title", "track", "date"))
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug("Mutagen failed for %s: %s", path, exc)
    if not is_valid_flac:
        is_valid_flac = _run_flac_test(path)

    score = 0
    if is_valid_flac:
        score += 4
    if audio_md5_ok:
        score += 2
    if tags_ok:
        score += 2
    if duration_ok:
        score += 2
    score = max(0, min(10, score))

    return {
        "path": str(path),
        "is_valid_flac": is_valid_flac,
        "audio_md5_ok": audio_md5_ok,
        "tags_ok": tags_ok,
        "duration_ok": duration_ok,
        "score": score,
    }
