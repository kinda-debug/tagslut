"""Centralised logging configuration."""

from __future__ import annotations

import logging
from typing import Optional


def configure_logging(level: str = "INFO", structured: bool = False) -> None:
    """Configure application logging."""

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    if structured:
        formatter: logging.Formatter = logging.Formatter("%(message)s")
    else:
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    handler: Optional[logging.Handler] = None
    for existing in root_logger.handlers:
        if isinstance(existing, logging.StreamHandler):
            handler = existing
            break

    if handler is None:
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)

    handler.setFormatter(formatter)


__all__ = ["configure_logging"]
