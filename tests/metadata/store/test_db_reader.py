from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tagslut.metadata.store.db_reader import get_eligible_files


def _make_files_db(tmp_path: Path, rows: list[tuple[str, dict | None]]) -> Path:
    db_path = tmp_path / "files.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT,
                duration REAL,
                metadata_json TEXT,
                enriched_at TEXT,
                canonical_isrc TEXT,
                zone TEXT,
                flac_ok INTEGER
            )
            """
        )
        for path, metadata in rows:
            conn.execute(
                """
                INSERT INTO files (path, duration, metadata_json, enriched_at, canonical_isrc, zone, flac_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    path,
                    123.0,
                    (json.dumps(metadata) if metadata is not None else None),
                    None,
                    None,
                    None,
                    1,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_isrc_extracted_from_filename_when_missing(tmp_path: Path) -> None:
    db_path = _make_files_db(
        tmp_path,
        [
            (
                "/music/0092. Avicii - Wake Me Up [SE7UQ2500010].flac",
                {},
            )
        ],
    )

    infos = list(get_eligible_files(db_path))
    assert len(infos) == 1
    assert infos[0].tag_isrc == "SE7UQ2500010"


def test_artist_title_extracted_from_filename_when_missing(tmp_path: Path) -> None:
    db_path = _make_files_db(
        tmp_path,
        [
            (
                "/music/0064. Kylie Minogue, Sia - Dance Alone (Kito Remix) [USAT22401968].flac",
                {},
            )
        ],
    )

    infos = list(get_eligible_files(db_path))
    assert len(infos) == 1
    assert infos[0].tag_artist == "Kylie Minogue, Sia"
    assert infos[0].tag_title == "Dance Alone (Kito Remix)"


def test_well_tagged_files_not_modified(tmp_path: Path) -> None:
    db_path = _make_files_db(
        tmp_path,
        [
            (
                "/music/0001. Wrong Artist - Wrong Title [SE7UQ2500010].flac",
                {"artist": "Tagged Artist", "title": "Tagged Title", "isrc": "GBUM71029604"},
            )
        ],
    )

    infos = list(get_eligible_files(db_path))
    assert len(infos) == 1
    assert infos[0].tag_artist == "Tagged Artist"
    assert infos[0].tag_title == "Tagged Title"
    assert infos[0].tag_isrc == "GBUM71029604"
