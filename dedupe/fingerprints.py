"""Chromaprint fingerprint helpers."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from shutil import which
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FingerprintResult:
    """Fingerprint payload generated via :func:`generate_chromaprint`."""

    path: Path
    fingerprint: str
    duration: float


def is_fpcalc_available() -> bool:
    """Return ``True`` if ``fpcalc`` is available on ``PATH``."""

    return which("fpcalc") is not None


def generate_chromaprint(
    path: Path,
    timeout: int = 30,
) -> Optional[FingerprintResult]:
    """Return the Chromaprint fingerprint for *path* or ``None`` on failure."""

    fpcalc = which("fpcalc")
    if fpcalc is None:
        logger.debug(
            "fpcalc not available; skipping fingerprint for %%s",
            path,
        )
        return None

    cmd = [fpcalc, "-json", str(path)]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("fpcalc invocation failed for %s: %s", path, exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "fpcalc returned non-zero exit status %s for %s",
            result.returncode,
            path,
        )
        return None

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse fpcalc output for %s: %s", path, exc)
        return None

    fingerprint = payload.get("fingerprint")
    duration = payload.get("duration")
    if not fingerprint or duration is None:
        return None

    return FingerprintResult(
        path=path,
        fingerprint=fingerprint,
        duration=float(duration),
    )


def similarity_ratio(first: str, second: str) -> float:
    """Return a similarity ratio between two fingerprint strings."""

    return SequenceMatcher(None, first, second).ratio()


def fingerprint_similarity(
    a: Optional[FingerprintResult],
    b: Optional[FingerprintResult],
) -> Optional[float]:
    """Return similarity between two fingerprints in ``[0, 1]`` or ``None``."""

    if a is None or b is None:
        return None
    return similarity_ratio(a.fingerprint, b.fingerprint)
