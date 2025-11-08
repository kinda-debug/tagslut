"""Top-level package for the unified dedupe toolkit."""

from . import cli, config, health, quarantine, sync

__all__ = [
    "cli",
    "config",
    "health",
    "quarantine",
    "sync",
]
