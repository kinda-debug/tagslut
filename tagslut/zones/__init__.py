"""Zone module entry point.

Provides zone constants, manager utilities, and assignment helpers.
"""

from tagslut.utils.zones import (  # noqa: F401
    Zone,
    ZoneConfig,
    ZoneManager,
    PathPriority,
    ZoneMatch,
    DEFAULT_PATH_PRIORITY,
    DEFAULT_ZONE_PRIORITY,
    LIBRARY_ZONES,
    QUARANTINE_ZONES,
    RECOVERABLE_ZONES,
    ZONE_ARCHIVE,
    ZONE_BAD,
    ZONE_DJPOOL,
    ZONE_GOOD,
    ZONE_LIBRARY,
    ZONE_QUARANTINE,
    coerce_zone,
    is_library_zone,
    is_quarantine_zone,
    is_recoverable_zone,
    load_zone_manager,
)
from tagslut.zones.assignment import determine_zone, update_zone_after_decision

__all__ = [
    "Zone",
    "ZoneConfig",
    "ZoneManager",
    "PathPriority",
    "ZoneMatch",
    "DEFAULT_PATH_PRIORITY",
    "DEFAULT_ZONE_PRIORITY",
    "LIBRARY_ZONES",
    "QUARANTINE_ZONES",
    "RECOVERABLE_ZONES",
    "ZONE_ARCHIVE",
    "ZONE_BAD",
    "ZONE_DJPOOL",
    "ZONE_GOOD",
    "ZONE_LIBRARY",
    "ZONE_QUARANTINE",
    "coerce_zone",
    "is_library_zone",
    "is_quarantine_zone",
    "is_recoverable_zone",
    "load_zone_manager",
    "determine_zone",
    "update_zone_after_decision",
]
