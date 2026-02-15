"""Zone assignment logic based on scan results and configured paths."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from tagslut.utils.zones import Zone, ZoneManager, get_default_zone_manager, is_quarantine_zone

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
    Assign a zone based on scan results and path classification.

    Priority:
    1. If the path is explicitly in a quarantine zone, keep it quarantine.
    2. Integrity failures or duplicates are forced to SUSPECT.
    3. Otherwise, use the zone derived from the path mapping.
    4. Fall back to default_zone or SUSPECT.
    """
    zm = zone_manager or get_default_zone_manager()
    match = zm.get_zone_for_path(file_path)

    if is_quarantine_zone(match.zone):
        logger.debug("Zone=quarantine (path match): %s", file_path)
        return Zone.QUARANTINE

    if not integrity_ok:
        logger.debug("Zone=suspect (integrity failed): %s", file_path)
        return Zone.SUSPECT

    if is_duplicate:
        logger.debug("Zone=suspect (duplicate detected): %s", file_path)
        return Zone.SUSPECT

    if match.zone:
        logger.debug("Zone=%s (path match): %s", match.zone, file_path)
        return match.zone

    return default_zone or Zone.SUSPECT


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
