import logging
from typing import Iterable, List, Sequence

from dedupe.storage.models import AudioFile, DuplicateGroup, Decision
from dedupe.core.keeper_selection import select_keeper_for_group
from dedupe.utils.zones import ZoneManager, load_zone_manager

logger = logging.getLogger("dedupe")

# Backward-compatible defaults
DEFAULT_ZONE_PRIORITY = ["accepted", "staging"]


def get_zone_priority(file: AudioFile, priorities: Sequence[str]) -> int:
    """Deprecated: retained for compatibility with legacy callers."""
    if file.zone and str(file.zone) in priorities:
        return priorities.index(str(file.zone))
    return 999


def assess_duplicate_group(
    group: DuplicateGroup,
    priority_order: List[str] | None = None,
    *,
    use_metadata_tiebreaker: bool = False,
    metadata_fields: Iterable[str] = ("artist", "album", "title"),
) -> List[Decision]:
    """
    Analyze a group of duplicates and return decisions for each file.

    This wraps the new keeper selection module while keeping the legacy API.
    """
    zone_manager = load_zone_manager()
    if priority_order:
        zone_manager = zone_manager.override_priorities(priority_order)

    result = select_keeper_for_group(
        group,
        zone_manager=zone_manager,
        use_metadata_tiebreaker=use_metadata_tiebreaker,
        metadata_fields=tuple(metadata_fields),
    )
    return result.decisions
