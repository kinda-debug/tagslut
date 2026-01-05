"""Upgrade legacy per-volume SQLite databases to the unified schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator, Iterable, List, Sequence

LIBRARY_COLUMNS: Sequence[str] = (
    "path",
    "size_bytes",
    "mtime",
    "checksum",
    "duration",
    "sample_rate",
    "bit_rate",
    "channels",
    "bit_depth",
    "tags_json",
    "fingerprint",
    "fingerprint_duration",
    "dup_group",
    "duplicate_rank",
    "is_canonical",
    "extra_json",
    "library_state",
    "flac_ok",
    "integrity_state",
    "zone",
)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS library_files(
    path TEXT PRIMARY KEY,
    size_bytes INTEGER,
    mtime REAL,
    checksum TEXT,
    duration REAL,
    sample_rate INTEGER,
    bit_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    tags_json TEXT,
    fingerprint TEXT,
    fingerprint_duration REAL,
    dup_group TEXT,
    duplicate_rank INTEGER,
    is_canonical INTEGER,
    extra_json TEXT,
    library_state TEXT DEFAULT 'accepted',
    flac_ok INTEGER,
    integrity_state TEXT,
    zone TEXT
);
"""


def _sanitise_path(value: object) -> str:
    """Return a UTF-8 safe, null-free path string."""

    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace")
    else:
        text = str(value) if value is not None else ""
    normalised = text.encode("utf-8", "replace").decode("utf-8", "replace")
    return normalised.replace("\x00", "")


def _read_legacy_columns(connection: sqlite3.Connection) -> List[str]:
    """Return column names from the legacy library_files table."""

    rows = connection.execute("PRAGMA table_info(library_files);").fetchall()
    if not rows:
        raise ValueError("Table 'library_files' missing in legacy database")
    return [row[1] for row in rows]


def _initialise_output(connection: sqlite3.Connection) -> None:
    """Create the target schema for the upgraded database."""

    connection.execute(CREATE_TABLE_SQL)


def _iter_legacy_rows(
    connection: sqlite3.Connection, columns: Iterable[str]
) -> Generator[sqlite3.Row, None, None]:
    """Yield rows from the legacy database using only known columns."""

    selected = ", ".join(columns)
    query = f"SELECT {selected} FROM library_files"
    for row in connection.execute(query):
        yield row


def _map_row(row: sqlite3.Row, legacy_columns: Iterable[str]) -> List[object]:
    """Translate a legacy row to the unified column order."""

    legacy_set = set(legacy_columns)
    mapped: List[object] = []
    for column in LIBRARY_COLUMNS:
        if column == "tags_json" and "tags_json" not in legacy_set:
            value = "{}"
        elif column == "library_state":
            value = "accepted"
        elif column == "zone":
            value = "accepted"
        elif column == "integrity_state":
            flac_ok = row["flac_ok"] if "flac_ok" in legacy_set else None
            value = "valid" if flac_ok == 1 else "recoverable"
        elif column in legacy_set:
            value = row[column]
        else:
            value = None

        if column == "path":
            value = _sanitise_path(value)

        mapped.append(value)
    return mapped


def upgrade_db(legacy_path: str, out_path: str) -> None:
    """
    Reads a legacy database at ``legacy_path`` and writes an upgraded copy to
    ``out_path``.

    The output schema matches the current ``library_files`` definition and is
    safe to attach and merge into ``library_final.db`` without modifying the
    source database.
    """

    output = Path(out_path)
    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(legacy_path) as legacy_conn:
        legacy_conn.row_factory = sqlite3.Row
        legacy_conn.text_factory = (
            lambda x: x.decode("utf-8", "replace")  # type: ignore[arg-type]
        )

        legacy_columns = _read_legacy_columns(legacy_conn)

        with sqlite3.connect(out_path) as output_conn:
            output_conn.row_factory = sqlite3.Row
            _initialise_output(output_conn)

            placeholders = ", ".join("?" for _ in LIBRARY_COLUMNS)
            insert_sql = (
                "INSERT INTO library_files ("
                + ", ".join(LIBRARY_COLUMNS)
                + f") VALUES ({placeholders})"
            )

            for row in _iter_legacy_rows(legacy_conn, legacy_columns):
                mapped = _map_row(row, legacy_columns)
                output_conn.execute(insert_sql, mapped)
