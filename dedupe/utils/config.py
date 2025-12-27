import logging
from pathlib import Path
from typing import Any, Dict

# Prefer standard library tomllib (Python 3.11+)
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

# Default locations to check for config
CONFIG_PATHS = [
    Path("config.toml"),
    Path.home() / ".config" / "dedupe" / "config.toml",
]

class Config:
    _instance = None
    _data: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """Load configuration from the first found valid source."""
        loaded = False
        for path in CONFIG_PATHS:
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        self._data = tomllib.load(f)
                    logging.info(f"Loaded configuration from {path}")
                    loaded = True
                    break
                except Exception as e:
                    logging.error(f"Failed to parse config at {path}: {e}")

        if not loaded:
            logging.warning("No configuration file found. Using defaults.")
            self._data = {}

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

def get_config() -> Config:
    """Public accessor for the singleton configuration."""
    return Config()
