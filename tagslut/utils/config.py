import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

# Prefer standard library tomllib (Python 3.11+)
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Default locations to check for config
CONFIG_PATHS = [
    Path("config.toml"),
    Path.home() / ".config" / "tagslut" / "config.toml",
]


@dataclass(frozen=True)
class ConfigKeySpec:
    expected_type: type | tuple[type, ...]
    default: Any
    required: bool = False


CONFIG_SCHEMA: dict[str, ConfigKeySpec] = {
    "db.path": ConfigKeySpec(str, None, required=True),
    "db.min_disk_space_mb": ConfigKeySpec(int, 50),
    "db.write_sanity_check": ConfigKeySpec(bool, True),
    "dj_pool_dir": ConfigKeySpec(str, "~/Music/DJPool"),
    "integrity.db_flush_interval": ConfigKeySpec(int, 60),
    "integrity.db_flush_interval_seconds": ConfigKeySpec(int, 60),
    "integrity.db_write_batch_size": ConfigKeySpec(int, 500),
    "integrity.min_disk_space_mb": ConfigKeySpec(int, 50),
    "integrity.parallel_workers": ConfigKeySpec((int, type(None)), None),
    "integrity.write_sanity_check": ConfigKeySpec(bool, True),
    "library.name": ConfigKeySpec(str, "COMMUNE"),
    "library.db_url": ConfigKeySpec(str, "sqlite:///~/.local/share/djtools/library.db"),
    "mgmt.audit_log_dir": ConfigKeySpec(str, None),
    "mgmt.duration.ok_max_delta_ms": ConfigKeySpec(int, 2000),
    "mgmt.duration.warn_max_delta_ms": ConfigKeySpec(int, 8000),
    "mgmt.m3u_dir": ConfigKeySpec(str, None),
    "rekordbox.use_canonical_matcher": ConfigKeySpec(bool, False),
    "tagslut.v3.dual_write": ConfigKeySpec(bool, False),
    "upload.use_canonical_matcher": ConfigKeySpec(bool, False),
    "v3.dual_write": ConfigKeySpec(bool, False),
}


def _clear_config_instance() -> None:
    """Internal helper to reset the config singleton (primarily for testing)."""
    Config._instance = None
    Config._data = {}
    Config._override_path = None


class Config:
    _instance = None
    _data: Dict[str, Any] = {}
    _override_path: Path | None = None

    def __new__(cls) -> "Config":
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load configuration from the first found valid source."""
        loaded = False

        env_path = os.getenv("TAGSLUT_CONFIG")
        candidate_paths = []
        if self._override_path:
            candidate_paths.append(self._override_path)
        if env_path:
            candidate_paths.append(Path(env_path))
        candidate_paths.extend(CONFIG_PATHS)

        for path in candidate_paths:
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        self._data = tomllib.load(f)

                    # Special check for test environment to avoid accidental root changes
                    if "PYTEST_CURRENT_TEST" in os.environ:
                        pass
                    else:
                        logging.info(f"Loaded configuration from {path}")

                    loaded = True
                    break
                except Exception as e:
                    logging.error(f"Failed to parse config at {path}: {e}")

        if not loaded:
            logging.warning("No configuration file found. Using defaults.")
            self._data = {}

        if os.getenv("TAGSLUT_STRICT_CONFIG") == "1":
            self.validate()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by key (dot notation supported)."""
        keys = key.split(".")
        value = self._data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    def items(self) -> Iterable[tuple[str, Any]]:
        return self._data.items()

    def values(self) -> Iterable[Any]:
        return self._data.values()

    def validate(self) -> list[str]:
        """Validate known keys, key types, and required-key presence."""
        issues: list[str] = []

        def _flatten(data: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    yield from _flatten(value, full_key)
                else:
                    yield full_key, value

        actual_keys = dict(_flatten(self._data))

        for key in sorted(actual_keys.keys()):
            if key not in CONFIG_SCHEMA:
                issues.append(f"Unknown config key: {key}")

        for key, spec in CONFIG_SCHEMA.items():
            value = self.get(key)
            if value is None:
                if spec.required:
                    issues.append(f"Missing required config key: {key}")
                continue
            if not isinstance(value, spec.expected_type):
                expected = (
                    ", ".join(t.__name__ for t in spec.expected_type)
                    if isinstance(spec.expected_type, tuple)
                    else spec.expected_type.__name__
                )
                issues.append(
                    f"Type mismatch for {key}: expected {expected}, got {type(value).__name__}"
                )

        for issue in issues:
            logging.warning(issue)

        return issues


def get_config(config_path: Path | None = None) -> Config:
    """Public accessor for the singleton configuration."""
    if "PYTEST_CURRENT_TEST" in os.environ:
        # Always clear or force reload in tests to avoid singleton contamination
        if config_path is not None:
            _clear_config_instance()
        elif os.getenv("TAGSLUT_CONFIG"):
            # If env var changed, we need to reload
            _clear_config_instance()

    config = Config()
    if config_path is not None and config_path != config._override_path:
        config._override_path = config_path
        config._load()
    return config
