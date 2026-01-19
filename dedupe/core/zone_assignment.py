"""Auto-assign zones based on scan results and file location.

Zones are determined after scanning, not before:
- integrity_ok=False → suspect (FLAC integrity check failed OR duration mismatch)
- is_duplicate=True → suspect (SHA256/AcoustID/etc duplicate)
- Clean file in library_root → accepted (canonical location)
- Clean file in staging_root → staging (ready for review/promotion)
- Otherwise → suspect (unknown location or unverified)

Integrity checks include:
- FLAC structure validation (flac -t)
- Duration validation (actual vs expected from MusicBrainz)
- Files with suspicious durations (stitched/truncated) are treated as integrity failures

This inverts the previous design where zones were manually assigned before scanning.
Now zones are a consequence of scan results.
"""
import logging
from pathlib import Path
from typing import Optional, Literal

logger = logging.getLogger("dedupe")

ZoneType = Literal["accepted", "staging", "suspect", "quarantine"]


def determine_zone(
    *,
    integrity_ok: bool,
    is_duplicate: bool,
    file_path: Path,
    library_root: Optional[Path] = None,
    staging_root: Optional[Path] = None,
) -> ZoneType:
    """
    Auto-assign zone based on scan results and file location.
    
    Logic:
    1. If integrity fails → suspect
    2. If duplicate detected → suspect
    3. If in library_root → accepted
    4. If in staging_root → staging
    5. Otherwise → suspect (needs review)
    
    Args:
        integrity_ok: True if file passed integrity check (flac -t)
        is_duplicate: True if SHA256 hash matches another file
        file_path: Path to the file being evaluated
        library_root: Path to canonical library (files here are "accepted")
        staging_root: Path to staging area (files here are "staging")
    
    Returns:
        Zone assignment: accepted, staging, suspect, or quarantine
    """
    
    # Integrity failures always go to suspect
    if not integrity_ok:
        logger.debug(f"Zone=suspect (integrity failed): {file_path}")
        return "suspect"
    
    # Duplicates always go to suspect for review
    if is_duplicate:
        logger.debug(f"Zone=suspect (duplicate detected): {file_path}")
        return "suspect"
    
    # Clean files in library are accepted
    if library_root and _is_under_path(file_path, library_root):
        logger.debug(f"Zone=accepted (in library): {file_path}")
        return "accepted"
    
    # Clean files in staging are ready to promote
    if staging_root and _is_under_path(file_path, staging_root):
        logger.debug(f"Zone=staging (in staging area): {file_path}")
        return "staging"
    
    # Everything else needs review
    logger.debug(f"Zone=suspect (location unknown): {file_path}")
    return "suspect"


def _is_under_path(file_path: Path, root: Path) -> bool:
    """Check if file_path is under root directory."""
    try:
        file_path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, RuntimeError):
        return False


def update_zone_after_decision(current_zone: ZoneType, decision: str) -> ZoneType:
    """
    Update zone after manual review decision.
    
    Args:
        current_zone: Current zone assignment
        decision: Decision action (KEEP, DROP, REVIEW, etc.)
    
    Returns:
        Updated zone
    """
    if decision == "DROP":
        return "quarantine"
    elif decision == "KEEP":
        return "staging"
    else:
        return current_zone
