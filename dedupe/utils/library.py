"""Helpers for working with COMMUNE library zones."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Literal

from dedupe.utils.config import Config

Zone = Literal["inbox", "staging", "accepted", "rejected"]

ZONE_ORDER: tuple[Zone, ...] = ("inbox", "staging", "accepted", "rejected")
DEDUPE_ZONES: tuple[Zone, ...] = ("staging", "accepted")


@dataclass(frozen=True)
class ZonePaths:
    """Resolved absolute paths for COMMUNE zones."""

    root: Path
    zones: Mapping[Zone, Path]
    yate_db: Path


def _resolve_path(root: Path, value: str) -> Path:
    """Resolve a configured path, supporting root-relative values."""

    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def load_zone_paths(config: Config) -> Optional[ZonePaths]:
    """Resolve COMMUNE zone paths from configuration."""

    library_root = config.get("library.root")
    zone_config = config.get("library.zones", {}) or {}
    if not library_root or not zone_config:
        return None

    root = Path(library_root)
    zones: dict[Zone, Path] = {}
    for zone in ZONE_ORDER:
        raw = zone_config.get(zone)
        if raw:
            zones[zone] = _resolve_path(root, str(raw))

    yate_raw = zone_config.get("yate_db", "_yate_db")
    yate_db = _resolve_path(root, str(yate_raw))
    return ZonePaths(root=root, zones=zones, yate_db=yate_db)


def identify_zone(path: Path, zone_paths: ZonePaths) -> Optional[Zone]:
    """Return the zone name for *path* when it matches a configured zone."""

    for zone, zone_root in zone_paths.zones.items():
        try:
            if zone_root in path.parents or path == zone_root:
                return zone
        except RuntimeError:
            continue
    return None


def is_ignored_path(path: Path, zone_paths: ZonePaths) -> bool:
    """Return ``True`` when *path* should be ignored entirely."""

    try:
        if zone_paths.yate_db in path.parents or path == zone_paths.yate_db:
            return True
    except RuntimeError:
        return False
    return False


def ensure_dedupe_zone(path: Path, zone_paths: ZonePaths) -> Zone:
    """Validate that *path* sits inside a dedupe-eligible zone."""

    zone = identify_zone(path, zone_paths)
    if zone is None:
        raise ValueError(f"Unable to determine zone for path: {path}")
    if zone not in DEDUPE_ZONES:
        raise ValueError(
            f"Zone '{zone}' is out of scope for dedupe: {path}"
        )
    return zone
