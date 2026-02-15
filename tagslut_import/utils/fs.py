"""Filesystem helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def ensure_directory(path: Path) -> None:
    """Ensure the provided directory exists."""

    path.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, data: bytes) -> None:
    """Write data to ``path`` atomically."""

    ensure_directory(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(data)
    os.replace(temp_path, path)


def list_files(directory: Path, *, suffixes: Iterable[str] | None = None) -> list[Path]:
    """Return a sorted list of files in ``directory`` optionally filtered by suffix."""

    ensure_directory(directory)
    paths = [p for p in directory.iterdir() if p.is_file()]
    if suffixes:
        suffix_set = set(suffixes)
        paths = [p for p in paths if p.suffix in suffix_set]
    return sorted(paths)


__all__ = ["ensure_directory", "atomic_write", "list_files"]
