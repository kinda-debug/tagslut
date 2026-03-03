"""Stage 0: filesystem discovery."""

from pathlib import Path
from typing import List

from tagslut.scan.constants import SUPPORTED_EXTENSIONS


def discover_paths(root: Path) -> List[Path]:
    """
    Recursively find all supported audio files under root.
    Skips 0-byte files. Returns sorted list for stable ordering.
    """
    found = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and p.stat().st_size > 0
    ]
    return sorted(found)
