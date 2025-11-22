"""Parser for R-Studio "Recognized Files" exports."""

from __future__ import annotations

import csv
import logging
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import utils

LOGGER = logging.getLogger(__name__)

RECOVERED_TABLE = "recovered_files"


@dataclass(slots=True)
class RecoveredFile:
    """Representation of a recovery candidate exported by R-Studio."""

    source_path: str
    suggested_name: str
    size_bytes: Optional[int]
    extension: Optional[str]


def initialise_database(connection: sqlite3.Connection) -> None:
    """Ensure the recovered files schema exists."""

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {RECOVERED_TABLE} (
            source_path TEXT PRIMARY KEY,
            suggested_name TEXT,
            size_bytes INTEGER,
            extension TEXT
        )
        """
    )


def _dialect_for(path: Path) -> Optional[csv.Dialect]:
    """Try to detect a CSV dialect.

    Return ``None`` when the file appears to be a plain newline-separated
    listing (no obvious delimiters). This lets the caller fall back to a
    simple line-oriented parser used by some R-Studio exports.
    """
    with path.open("r", encoding="utf8", errors="ignore") as handle:
        sample = handle.read(8192)
    # Inspect the first non-comment line: some R-Studio exports include
    # header/metadata lines (starting with ':#') that may contain
    # semicolons or other punctuation. If the first meaningful line does
    # not contain common CSV delimiters, treat the file as a plain
    # newline-separated listing.
    first_line = None
    for raw in sample.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(":#"):
            continue
        first_line = s
        break
    if first_line is not None and not any(d in first_line for d in (",", "\t", ";")):
        return None
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel_tab
    return dialect


def parse_export(path: Path) -> Iterator[RecoveredFile]:
    """Yield :class:`RecoveredFile` rows parsed from *path*.

    Supports both CSV-style exports and simple newline-separated listings.
    """

    dialect = _dialect_for(path)
    # Plain line-oriented export (no CSV delimiters detected)
    if dialect is None:
        with path.open("r", encoding="utf8", errors="ignore") as handle:
            for raw in handle:
                line = raw.rstrip("\n\r")
                if not line:
                    continue
                # Skip R-Studio metadata/comment lines starting with ':#'
                if line.startswith(":#"):
                    continue
                source = line.strip()
                if source:
                    yield RecoveredFile(
                        source_path=utils.normalise_path(source),
                        suggested_name="",
                        size_bytes=None,
                        extension=None,
                    )
        return

    # CSV-style export
    with path.open(
        "r",
        encoding="utf8",
        errors="ignore",
        newline="",
    ) as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        for row in reader:
            source = (
                row.get("Source Name")
                or row.get("File name")
                or row.get("Name")
            )
            suggested = (
                row.get("New File Name")
                or row.get("Suggested Name")
                or ""
            )
            size_field = row.get("Size") or row.get("File Size")
            size = utils.safe_int(size_field)
            extension = (
                row.get("Ext")
                or row.get("Extension")
                or ""
            ).strip() or None
            if source:
                yield RecoveredFile(
                    source_path=utils.normalise_path(source),
                    suggested_name=suggested.strip(),
                    size_bytes=size,
                    extension=extension,
                )


def load_into_database(
    records: Iterable[RecoveredFile],
    database: Path,
) -> int:
    """Persist *records* into *database* and return the stored row count."""

    database = Path(utils.normalise_path(str(database)))
    utils.ensure_parent_directory(database)
    db = utils.DatabaseContext(database)
    count = 0
    with db.connect() as connection:
        initialise_database(connection)
        connection.executemany(
            f"""
            INSERT INTO {RECOVERED_TABLE} (
                source_path,
                suggested_name,
                size_bytes,
                extension
            )
            VALUES (
                :source_path,
                :suggested_name,
                :size_bytes,
                :extension
            )
            ON CONFLICT(source_path) DO UPDATE SET
                suggested_name=excluded.suggested_name,
                size_bytes=excluded.size_bytes,
                extension=excluded.extension
            """,
            [asdict(record) for record in records],
        )
        count = connection.execute(
            f"SELECT COUNT(*) FROM {RECOVERED_TABLE}"
        ).fetchone()[0]
    LOGGER.info("Recorded %s recovered files in %s", count, database)
    return int(count)
