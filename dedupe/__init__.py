"""Top-level package for the unified dedupe toolkit."""

from . import config, health, quarantine, sync

__all__ = [
    "config",
    "health",
    "quarantine",
    "sync",
]
