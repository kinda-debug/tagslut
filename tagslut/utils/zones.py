"""Zone management for tagslut.

Zones are first-class trust/lifecycle stages. They must remain explicit,
visible in the DB, and central to keeper selection and safety logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
import logging
import os

logger = logging.getLogger("tagslut.zones")


class Zone(StrEnum):
    """Canonical zone identifiers."""

    ACCEPTED = "accepted"
    ARCHIVE = "archive"
    STAGING = "staging"
    SUSPECT = "suspect"
    QUARANTINE = "quarantine"
    # Legacy/optional zones kept for backward compatibility
    INBOX = "inbox"
    REJECTED = "rejected"


DEFAULT_ZONE_PRIORITY: dict[Zone, int] = {
    Zone.ACCEPTED: 10,
    Zone.ARCHIVE: 20,
    Zone.STAGING: 30,
    Zone.INBOX: 35,
    Zone.SUSPECT: 40,
    Zone.REJECTED: 45,
    Zone.QUARANTINE: 50,
}

DEFAULT_PATH_PRIORITY = 1000

LIBRARY_ZONES: frozenset[Zone] = frozenset({Zone.ACCEPTED, Zone.ARCHIVE})
QUARANTINE_ZONES: frozenset[Zone] = frozenset({Zone.QUARANTINE})
RECOVERABLE_ZONES: frozenset[Zone] = frozenset(
    {Zone.ACCEPTED, Zone.ARCHIVE, Zone.STAGING, Zone.SUSPECT, Zone.INBOX}
)


@dataclass(frozen=True)
class ZoneConfig:
    zone: Zone
    paths: tuple[Path, ...]
    priority: int
    description: str | None = None


@dataclass(frozen=True)
class PathPriority:
    path: Path
    priority: int
    description: str | None = None


@dataclass(frozen=True)
class ZoneMatch:
    zone: Zone
    zone_priority: int
    path_priority: int
    matched_path: Path | None
    source: str


class ZoneManager:
    """Load zone configuration, map paths to zones, and expose priorities."""

    def __init__(
        self,
        zone_configs: Iterable[ZoneConfig],
        path_priorities: Iterable[PathPriority] | None = None,
        default_zone: Zone = Zone.SUSPECT,
        source: str = "config",
    ) -> None:
        self._zones: dict[Zone, ZoneConfig] = {zc.zone: zc for zc in zone_configs}
        self._path_priorities: tuple[PathPriority, ...] = tuple(path_priorities or ())
        self._default_zone = default_zone
        self._source = source

    @property
    def source(self) -> str:
        return self._source

    @property
    def default_zone(self) -> Zone:
        return self._default_zone

    def zones(self) -> Sequence[ZoneConfig]:
        return tuple(self._zones.values())

    def path_priorities(self) -> Sequence[PathPriority]:
        return self._path_priorities

    def has_library_zones(self) -> bool:
        return Zone.ACCEPTED in self._zones

    def get_zone_for_path(self, path: Path) -> ZoneMatch:
        """Return the best zone match for a path (longest-prefix match)."""
        path = _expand_path(path)
        best_match: tuple[int, ZoneConfig, Path] | None = None
        for zone_config in self._zones.values():
            for root in zone_config.paths:
                if _is_under_path(path, root):
                    score = len(str(root))
                    if best_match is None or score > best_match[0]:
                        best_match = (score, zone_config, root)

        if best_match is None:
            zone = self._default_zone
            return ZoneMatch(
                zone=zone,
                zone_priority=self.zone_priority(zone),
                path_priority=self.path_priority(path),
                matched_path=None,
                source=self._source,
            )

        _, zone_config, root = best_match
        return ZoneMatch(
            zone=zone_config.zone,
            zone_priority=zone_config.priority,
            path_priority=self.path_priority(path),
            matched_path=root,
            source=self._source,
        )

    def zone_priority(self, zone: Zone | str | None) -> int:
        z = coerce_zone(zone)
        if z and z in self._zones:
            return self._zones[z].priority
        if z:
            return zone_priority(z)
        return DEFAULT_PATH_PRIORITY

    def path_priority(self, path: Path) -> int:
        """Return the best path priority for a given path."""
        path = _expand_path(path)
        best: tuple[int, int] | None = None
        for entry in self._path_priorities:
            if _is_under_path(path, entry.path):
                score = len(str(entry.path))
                candidate = (score, entry.priority)
                if best is None or candidate[0] > best[0] or (
                    candidate[0] == best[0] and candidate[1] < best[1]
                ):
                    best = candidate
        if best is None:
            return DEFAULT_PATH_PRIORITY
        return best[1]

    def override_priorities(self, zone_order: Sequence[str]) -> "ZoneManager":
        """Return a new ZoneManager with zone priorities overridden by order."""
        overrides: dict[Zone, int] = {}
        for idx, name in enumerate(zone_order, start=1):
            zone = coerce_zone(name)
            if zone:
                overrides[zone] = idx
        if not overrides:
            return self

        zone_configs: list[ZoneConfig] = []
        for zone_config in self._zones.values():
            priority = overrides.get(zone_config.zone, zone_config.priority)
            zone_configs.append(
                ZoneConfig(
                    zone=zone_config.zone,
                    paths=zone_config.paths,
                    priority=priority,
                    description=zone_config.description,
                )
            )
        return ZoneManager(
            zone_configs=zone_configs,
            path_priorities=self._path_priorities,
            default_zone=self._default_zone,
            source=f"{self._source}+override",
        )


def zone_priority(zone: Zone) -> int:
    """Default zone priority (lower = higher priority)."""
    return DEFAULT_ZONE_PRIORITY.get(zone, DEFAULT_PATH_PRIORITY)


def is_library_zone(zone: Zone | str | None) -> bool:
    z = coerce_zone(zone)
    return bool(z and z in LIBRARY_ZONES)


def is_quarantine_zone(zone: Zone | str | None) -> bool:
    z = coerce_zone(zone)
    return bool(z and z in QUARANTINE_ZONES)


def is_recoverable_zone(zone: Zone | str | None) -> bool:
    z = coerce_zone(zone)
    return bool(z and z in RECOVERABLE_ZONES)


def coerce_zone(value: Zone | str | None) -> Zone | None:
    if value is None:
        return None
    if isinstance(value, Zone):
        return value
    try:
        return Zone(str(value).lower())
    except ValueError:
        return None


def load_zone_manager(
    *,
    config: Optional[Mapping[str, Any]] = None,
    config_path: Optional[Path] = None,
) -> ZoneManager:
    """Load zones from YAML config, TOML config mapping, or environment."""
    # 1) Explicit YAML path
    if config_path:
        data = _load_yaml(config_path)
        return _zone_manager_from_mapping(data, source=str(config_path))

    # 2) Env var pointing to YAML
    env_path = os.getenv("TAGSLUT_ZONES_CONFIG")
    if env_path:
        data = _load_yaml(Path(env_path))
        return _zone_manager_from_mapping(data, source=str(env_path))

    # 3) TOML config mapping (if supplied)
    if config is not None:
        zm = _zone_manager_from_toml(config)
        if zm is not None:
            return zm

    # 4) Environment fallback
    return _zone_manager_from_env()


_DEFAULT_ZONE_MANAGER: ZoneManager | None = None


def get_default_zone_manager() -> ZoneManager:
    """Return a cached ZoneManager for the current process."""
    global _DEFAULT_ZONE_MANAGER
    if _DEFAULT_ZONE_MANAGER is None:
        _DEFAULT_ZONE_MANAGER = load_zone_manager()
    return _DEFAULT_ZONE_MANAGER


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load zone config files. "
            "Install it with 'pip install pyyaml'."
        ) from exc

    with Path(path).expanduser().open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"Zone config must be a mapping at top-level: {path}")
    return data


def _zone_manager_from_mapping(data: Mapping[str, Any], *, source: str) -> ZoneManager:
    zones_data = data.get("zones", {}) if isinstance(data, Mapping) else {}
    default_zone = coerce_zone(data.get("defaults", {}).get("zone")) if isinstance(data.get("defaults"), Mapping) else None
    default_zone = default_zone or Zone.SUSPECT

    base_root = None
    roots = data.get("roots") if isinstance(data, Mapping) else None
    if isinstance(roots, Mapping):
        root_candidate = roots.get("base") or roots.get("library")
        if root_candidate:
            base_root = Path(str(root_candidate))

    zone_configs: list[ZoneConfig] = []
    if isinstance(zones_data, Mapping):
        for raw_zone, payload in zones_data.items():
            zone = coerce_zone(raw_zone)
            if zone is None:
                logger.warning("Ignoring unknown zone in config: %s", raw_zone)
                continue
            if not isinstance(payload, Mapping):
                logger.warning("Zone config for %s must be a mapping", raw_zone)
                continue
            raw_paths = payload.get("paths", [])
            if isinstance(raw_paths, str):
                raw_paths = [raw_paths]
            paths: list[Path] = []
            if isinstance(raw_paths, Iterable):
                for raw in raw_paths:
                    if raw is None:
                        continue
                    path_obj = _resolve_path(str(raw), base_root)
                    paths.append(path_obj)
            priority = payload.get("priority")
            if priority is None:
                priority = DEFAULT_ZONE_PRIORITY.get(zone, DEFAULT_PATH_PRIORITY)
            try:
                priority_int = int(priority)
            except (TypeError, ValueError):
                priority_int = DEFAULT_ZONE_PRIORITY.get(zone, DEFAULT_PATH_PRIORITY)
            description = payload.get("description") if isinstance(payload.get("description"), str) else None
            zone_configs.append(
                ZoneConfig(
                    zone=zone,
                    paths=tuple(paths),
                    priority=priority_int,
                    description=description,
                )
            )

    path_priorities = _parse_path_priorities(data.get("path_priorities"), base_root)

    if not zone_configs:
        logger.warning("Zone config %s did not define any zones; falling back to env", source)
        return _zone_manager_from_env()

    return ZoneManager(
        zone_configs=zone_configs,
        path_priorities=path_priorities,
        default_zone=default_zone,
        source=source,
    )


def _zone_manager_from_toml(config: Mapping[str, Any]) -> ZoneManager | None:
    library_root = _get_nested(config, "library", "root")
    zone_mapping = _get_nested(config, "library", "zones")
    if not library_root or not isinstance(zone_mapping, Mapping):
        return None

    base_root = Path(str(library_root))
    zone_configs: list[ZoneConfig] = []
    for raw_zone, raw_path in zone_mapping.items():
        zone = coerce_zone(raw_zone)
        if zone is None:
            continue
        if raw_path is None:
            continue
        path_obj = _resolve_path(str(raw_path), base_root)
        zone_configs.append(
            ZoneConfig(
                zone=zone,
                paths=(path_obj,),
                priority=DEFAULT_ZONE_PRIORITY.get(zone, DEFAULT_PATH_PRIORITY),
            )
        )

    if not zone_configs:
        return None

    return ZoneManager(
        zone_configs=zone_configs,
        path_priorities=(),
        default_zone=Zone.SUSPECT,
        source="config.toml",
    )


def _zone_manager_from_env() -> ZoneManager:
    env_map: dict[str, Zone] = {
        "VOLUME_LIBRARY": Zone.ACCEPTED,
        "VOLUME_ARCHIVE": Zone.ARCHIVE,
        "VOLUME_STAGING": Zone.STAGING,
        "VOLUME_INBOX": Zone.INBOX,
        "VOLUME_SUSPECT": Zone.SUSPECT,
        "VOLUME_REJECTED": Zone.REJECTED,
        "VOLUME_QUARANTINE": Zone.QUARANTINE,
    }

    zone_configs: list[ZoneConfig] = []
    for env_var, zone in env_map.items():
        raw = os.getenv(env_var)
        if not raw:
            continue
        path_obj = _resolve_path(raw, None)
        zone_configs.append(
            ZoneConfig(
                zone=zone,
                paths=(path_obj,),
                priority=DEFAULT_ZONE_PRIORITY.get(zone, DEFAULT_PATH_PRIORITY),
            )
        )

    if not zone_configs:
        # Default to empty config; map everything to suspect
        logger.warning("No zone configuration found; defaulting all paths to suspect")
        zone_configs = [
            ZoneConfig(zone=Zone.SUSPECT, paths=tuple(), priority=DEFAULT_ZONE_PRIORITY[Zone.SUSPECT])
        ]

    return ZoneManager(
        zone_configs=zone_configs,
        path_priorities=(),
        default_zone=Zone.SUSPECT,
        source="env",
    )


def _parse_path_priorities(raw: Any, base_root: Path | None) -> list[PathPriority]:
    priorities: list[PathPriority] = []
    if isinstance(raw, Mapping):
        for raw_path, priority in raw.items():
            try:
                path_obj = _resolve_path(str(raw_path), base_root)
                priorities.append(PathPriority(path=path_obj, priority=int(priority)))
            except (TypeError, ValueError):
                continue
    elif isinstance(raw, Sequence):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            raw_path = item.get("path")
            priority = item.get("priority")
            if raw_path is None or priority is None:
                continue
            try:
                path_obj = _resolve_path(str(raw_path), base_root)
                priorities.append(
                    PathPriority(
                        path=path_obj,
                        priority=int(priority),
                        description=item.get("description"),
                    )
                )
            except (TypeError, ValueError):
                continue
    return priorities


def _get_nested(mapping: Mapping[str, Any], *keys: str) -> Any:
    cur: Any = mapping
    for key in keys:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


def _resolve_path(raw: str, base_root: Path | None) -> Path:
    value = os.path.expandvars(os.path.expanduser(raw))
    path_obj = Path(value)
    if not path_obj.is_absolute() and base_root is not None:
        path_obj = base_root / path_obj
    return path_obj


def _expand_path(path: Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def _is_under_path(path: Path, root: Path) -> bool:
    try:
        return path.resolve().relative_to(root.resolve()) is not None
    except (ValueError, RuntimeError):
        return False
