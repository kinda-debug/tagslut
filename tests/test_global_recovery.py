"""Unit tests covering the global recovery workflow."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dedupe import global_recovery


def _prepare_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    global_recovery.ensure_schema(connection)
    return connection


def test_resolver_prefers_high_quality_candidate(tmp_path):
    db_path = tmp_path / "global.db"
    connection = _prepare_database(db_path)
    try:
        connection.execute(
            f"""
            INSERT INTO {global_recovery.FILES_TABLE} (
                source_root,
                path,
                relative_path,
                filename,
                extension,
                size_bytes,
                mtime,
                duration,
                sample_rate,
                bit_rate,
                checksum,
                tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/Volumes/Primary",
                "/Volumes/Primary/Artist/Album/01 - Track.flac",
                "Artist/Album/01 - Track.flac",
                "01 - Track.flac",
                "flac",
                100,
                0.0,
                300.0,
                48000,
                1000000,
                "aaa",
                json.dumps(
                    {
                        "artist": "Artist",
                        "album": "Album",
                        "tracknumber": "01",
                        "title": "Track",
                    }
                ),
            ),
        )
        connection.execute(
            f"""
            INSERT INTO {global_recovery.FILES_TABLE} (
                source_root,
                path,
                relative_path,
                filename,
                extension,
                size_bytes,
                mtime,
                duration,
                sample_rate,
                bit_rate,
                checksum,
                tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/Volumes/Archive",
                "/Volumes/Archive/Artist/Album/01 - Track.mp3",
                "Artist/Album/01 - Track.mp3",
                "01 - Track.mp3",
                "mp3",
                60,
                0.0,
                250.0,
                44100,
                320000,
                "bbb",
                json.dumps(
                    {
                        "artist": "Artist",
                        "album": "Album",
                        "tracknumber": "01",
                        "title": "Track",
                    }
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    out_prefix = tmp_path / "reports" / "global_recovery"
    config = global_recovery.ResolverConfig(
        database=db_path,
        out_prefix=out_prefix,
    )
    results = global_recovery.resolve_database(config)
    assert results, "Expected at least one resolution result"
    result = next(res for res in results if res.best)
    assert result.best is not None
    assert result.best.path.endswith("Track.flac")
    assert not result.needs_manual

    keepers_csv = out_prefix.with_name(f"{out_prefix.name}_keepers.csv")
    assert keepers_csv.exists(), "Resolver should emit keepers CSV"


def test_resolver_uses_tags_for_group_key(tmp_path):
    db_path = tmp_path / "tags.db"
    connection = _prepare_database(db_path)
    try:
        connection.execute(
            f"""
            INSERT INTO {global_recovery.FILES_TABLE} (
                source_root,
                path,
                relative_path,
                filename,
                extension,
                size_bytes,
                mtime,
                duration,
                sample_rate,
                bit_rate,
                checksum,
                tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "/Volumes/Primary",
                "/Volumes/Primary/Artist/Album/Track.flac",
                "Artist/Album/Track.flac",
                "Track.flac",
                "flac",
                80,
                0.0,
                200.0,
                44100,
                900000,
                "ccc",
                json.dumps(
                    {
                        "artist": "Artist",
                        "album": "Album",
                        "tracknumber": "01",
                        "title": "Track",
                    }
                ),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    out_prefix = tmp_path / "tags" / "global_recovery"
    results = global_recovery.resolve_database(
        global_recovery.ResolverConfig(
            database=db_path,
            out_prefix=out_prefix,
        )
    )
    assert results[0].group_key.startswith("artist::album")


def test_fragment_only_group_marked_manual(tmp_path):
    db_path = tmp_path / "fragments.db"
    connection = _prepare_database(db_path)
    try:
        connection.execute(
            f"""
            INSERT INTO {global_recovery.FRAGMENTS_TABLE} (
                source_path,
                suggested_name,
                filename,
                extension,
                size_bytes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "/recovered/Track.wav",
                "Artist - Album - Track",
                "Track.wav",
                "wav",
                50,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    out_prefix = tmp_path / "fragments" / "global_recovery"
    results = global_recovery.resolve_database(
        global_recovery.ResolverConfig(
            database=db_path,
            out_prefix=out_prefix,
        )
    )
    assert results
    manual = results[0]
    assert manual.best is None or manual.needs_manual
