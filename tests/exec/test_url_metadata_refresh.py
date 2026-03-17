from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.exec.url_metadata_refresh import refresh_track_hub_from_tracks_csv
from tagslut.storage.schema import init_db


def _init_db_file(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()


def test_refresh_track_hub_from_tracks_csv_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    _init_db_file(db_path)

    tracks_csv = tmp_path / "precheck_tracks_extracted_20260317_000000.csv"
    tracks_csv.write_text(
        "\n".join(
            [
                "domain,source_link,normalized_link,track_id,title,artist,album,isrc,duration_ms",
                "tidal,https://tidal.com/browse/playlist/x,https://tidal.com/browse/track/1,1,Test Track,Test Artist,Test Album,USTEST001,180000",
                "tidal,https://tidal.com/browse/playlist/x,https://tidal.com/browse/track/,,Missing Id,Artist,Album,,",
                "",
            ]
        ),
        encoding="utf-8",
    )

    stats1, _ = refresh_track_hub_from_tracks_csv(db_path=db_path, tracks_csv=tracks_csv)
    stats2, _ = refresh_track_hub_from_tracks_csv(db_path=db_path, tracks_csv=tracks_csv)

    assert stats1.tracks_seen == 2
    assert stats1.tracks_written == 1
    assert stats1.tracks_skipped_missing_id == 1

    assert stats2.tracks_written == 1

    conn = sqlite3.connect(str(db_path))
    try:
        library_tracks_count = int(conn.execute("SELECT COUNT(*) FROM library_tracks").fetchone()[0])
        library_sources_count = int(conn.execute("SELECT COUNT(*) FROM library_track_sources").fetchone()[0])
    finally:
        conn.close()

    assert library_tracks_count == 1
    assert library_sources_count == 1

