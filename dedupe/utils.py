"""Utility helpers shared across dedupe components."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".flac",
    ".wav",
    ".aiff",
    ".aif",
    ".mp3",
    ".m4a",
    ".ogg",
    ".aac",
}


@dataclass(slots=True)
class DatabaseContext:
    """Thin wrapper that manages SQLite connections with sane defaults."""

    path: Path

    def connect(self) -> sqlite3.Connection:
        """Return a SQLite connection with WAL + busy timeout configured."""

        logger.debug("Opening SQLite database at %s", self.path)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
        return connection


def ensure_parent_directory(path: Path) -> None:
    """Create the parent directory for *path* if it does not already exist."""

    parent = path.expanduser().resolve().parent
    parent.mkdir(parents=True, exist_ok=True)


def iter_audio_files(root: Path) -> Iterator[Path]:
    """Yield audio files underneath *root* recursively."""

    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        if entry.suffix.lower() in AUDIO_EXTENSIONS:
            yield entry


def is_audio_file(pathish: str | Path) -> bool:
    """Return ``True`` when *pathish* has a recognised audio extension.

    This compatibility shim accepts either a :class:`Path` or a string filename,
    mirroring behaviour expected by older callers.
    """

    try:
        suffix = Path(pathish).suffix.lower()
    except Exception:
        return False
    return suffix in AUDIO_EXTENSIONS


def compute_md5(path: Path, chunk_size: int = 1 << 16) -> str:
    """Return the hexadecimal MD5 checksum for *path*."""

    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(chunk_size),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    """Load JSON data from *path* if it exists, else return an empty dict."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf8") as handle:
        return json.load(handle)


def safe_int(value: Optional[str]) -> Optional[int]:
    """Attempt to coerce *value* to an ``int``; return ``None`` on failure."""

    if value is None:
        return None
    with contextlib.suppress(ValueError):
        return int(value)
    return None


def safe_float(value: Optional[str]) -> Optional[float]:
    """Attempt to coerce *value* to ``float``; return ``None`` on failure."""

    if value is None:
        return None
    with contextlib.suppress(ValueError):
        return float(value)
    return None


def normalise_path(value: str) -> str:
    """Return a NFC-normalised absolute POSIX path for *value*.

    Paths are expanded (``~`` handling), resolved without requiring the target
    to exist, and coerced to Unicode NFC to avoid duplicate records caused by
    differing normalisation forms on disk or within SQLite.
    """

    resolved = Path(value).expanduser().resolve(strict=False)
    return unicodedata.normalize("NFC", resolved.as_posix())


def chunks(items: Iterable[Path], size: int) -> Iterator[list[Path]]:
    """Yield *items* in fixed-length chunks."""

    batch: list[Path] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


@contextlib.contextmanager
def temporary_cwd(path: Path) -> Iterator[None]:
    """Temporarily change the working directory to *path*."""

    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def as_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row into a plain ``dict``."""

    return {key: row[key] for key in row.keys()}
