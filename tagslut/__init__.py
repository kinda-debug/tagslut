"""Tagslut compatibility package mapped to the dedupe implementation.

This package provides rebranded import/entrypoint surfaces while the core
implementation remains under ``dedupe`` during migration.
"""

from dedupe.cli.main import cli

__all__ = ["cli"]
