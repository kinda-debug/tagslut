from __future__ import annotations

import sqlite3

from tagslut.storage.queries import _row_to_audiofile
from tagslut.zones import Zone


def _row_from_query(query: str, params: tuple[object, ...]) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query, params).fetchone()
        assert row is not None
        return row
    finally:
        conn.close()


def test_row_to_audiofile_with_all_expected_columns() -> None:
    row = _row_from_query(
        """
        SELECT
            ? AS path,
            ? AS library,
            ? AS zone,
            ? AS mtime,
            ? AS size,
            ? AS checksum,
            ? AS streaminfo_md5,
            ? AS sha256,
            ? AS duration,
            ? AS bit_depth,
            ? AS sample_rate,
            ? AS bitrate,
            ? AS metadata_json,
            ? AS flac_ok,
            ? AS acoustid,
            ? AS integrity_state
        """,
        (
            "/music/a.flac",
            "COMMUNE",
            "accepted",
            123.0,
            456,
            "abc",
            "md5",
            "sha",
            321.5,
            24,
            44100,
            1000,
            '{"artist":"Test"}',
            1,
            "acoustid-1",
            "valid",
        ),
    )

    audio = _row_to_audiofile(row)
    assert str(audio.path) == "/music/a.flac"
    assert audio.library == "COMMUNE"
    assert audio.zone == Zone.ACCEPTED
    assert audio.flac_ok is True
    assert audio.metadata["artist"] == "Test"


def test_row_to_audiofile_with_missing_optional_columns() -> None:
    row = _row_from_query(
        "SELECT ? AS path, ? AS checksum, ? AS metadata_json",
        ("/music/b.flac", "def", "{}"),
    )

    audio = _row_to_audiofile(row)
    assert str(audio.path) == "/music/b.flac"
    assert audio.checksum == "def"
    assert audio.library is None
    assert audio.zone is None
    assert audio.duration is None
