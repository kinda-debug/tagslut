from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

CAMELOT_KEYS = {
    "1A",
    "2A",
    "3A",
    "4A",
    "5A",
    "6A",
    "7A",
    "8A",
    "9A",
    "10A",
    "11A",
    "12A",
    "1B",
    "2B",
    "3B",
    "4B",
    "5B",
    "6B",
    "7B",
    "8B",
    "9B",
    "10B",
    "11B",
    "12B",
}


def is_keyfinder_available() -> bool:
    """Check if keyfinder-cli is installed and on PATH."""
    return shutil.which("keyfinder-cli") is not None


def detect_key(path: Path, timeout_sec: int = 30) -> str | None:
    """Detect musical key using KeyFinder CLI.

    Returns Camelot notation (e.g. '11B', '4A') or None if:
    - keyfinder-cli not installed
    - Detection fails or times out
    - Output is not a valid Camelot key

    Graceful degradation: never raises, always returns str | None.
    """
    if not is_keyfinder_available():
        log.debug("keyfinder-cli not found on PATH, skipping key detection")
        return None

    try:
        result = subprocess.run(
            ["keyfinder-cli", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            log.warning("keyfinder-cli failed for %s: %s", path, result.stderr.strip())
            return None

        key = result.stdout.strip().upper()

        if key in CAMELOT_KEYS:
            return key

        log.warning("keyfinder-cli returned unexpected key format: %r for %s", key, path)
        return None

    except subprocess.TimeoutExpired:
        log.warning("keyfinder-cli timed out for %s", path)
        return None
    except OSError as exc:
        log.warning("keyfinder-cli OS error for %s: %s", path, exc)
        return None

