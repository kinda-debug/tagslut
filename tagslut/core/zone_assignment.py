"""Zone assignment logic based on scan results and configured paths."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from tagslut.utils.zones import Zone, ZoneManager

logger = logging.getLogger("tagslut")


def determine_zone(
    *,
    integrity_ok: bool,
    is_duplicate: bool,
    file_path: Path,
    zone_manager: Optional[ZoneManager] = None,
    default_zone: Zone | None = None,
) -> Zone:
    """
    Assign a zone based on scan results only.

    Priority:
    1. Integrity failures or duplicates -> SUSPECT.
    2. Otherwise -> default_zone (if provided) or STAGING.

    Path-based zones are ignored to keep assignment tool-driven.
    """
    if not integrity_ok:
        logger.debug("Zone=suspect (integrity failed): %s", file_path)
        return Zone.SUSPECT

    if is_duplicate:
        logger.debug("Zone=suspect (duplicate detected): %s", file_path)
        return Zone.SUSPECT

    return default_zone or Zone.STAGING


def update_zone_after_decision(current_zone: Zone, decision: str) -> Zone:
    """
    Update zone after manual review decision.

    Args:
        current_zone: Current zone assignment
        decision: Decision action (KEEP, DROP, REVIEW, etc.)

    Returns:
        Updated zone
    """
    decision = decision.upper()
    if decision == "DROP":
        return Zone.QUARANTINE
    if decision == "KEEP":
        return Zone.STAGING
    return current_zone
