"""
tagslut.core
-----------
Pure business logic for the FLAC deduplication system.
This module contains no direct user interaction or CLI logic.
"""

from tagslut.core.metadata import extract_metadata
from tagslut.core.integrity import check_flac_integrity
from tagslut.core.hashing import calculate_file_hash

__all__ = [
    "extract_metadata",
    "check_flac_integrity",
    "calculate_file_hash",
]
