"""Parse R-Studio export files into the recovered_files database."""

from __future__ import annotations

import csv
import logging
import sqlite3
from dataclasses import dataclass
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


def _dialect_for(path: Path) -> csv.Dialect:
    with path.open("r", encoding="utf8", errors="ignore") as handle:
        sample = handle.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel_tab
    return dialect


def parse_export(path: Path) -> Iterator[RecoveredFile]:
    """Yield :class:`RecoveredFile` rows parsed from *path*."""

    dialect = _dialect_for(path)
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
    *,
    create_db: bool = False,
    allow_repo_db: bool = False,
) -> int:
    """Persist *records* into *database* and return the stored row count."""

    db = utils.DatabaseContext(
        database,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
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
            [record.__dict__ for record in records],
        )
        count = connection.execute(
            f"SELECT COUNT(*) FROM {RECOVERED_TABLE}"
        ).fetchone()[0]
    LOGGER.info("Recorded %s recovered files in %s", count, database)
    return int(count)
