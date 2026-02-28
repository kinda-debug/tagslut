import sqlite3

import pytest

from tagslut.core.pre_flight import PreFlightResolver
from tagslut.filters.identity_resolver import TrackIntent
from tagslut.storage.schema import init_db


@pytest.fixture
def db_with_track():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    # Insert a known CD-quality track (rank 4)
    conn.execute(
        """
        INSERT INTO files (
            path, checksum, duration, bit_depth, sample_rate, bitrate,
            metadata_json, quality_rank, canonical_isrc, canonical_artist,
            canonical_title, beatport_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "/music/artist - track.flac",
            "abc123",
            240.0,
            16,
            44100,
            0,
            "{}",
            4,
            "USABC1234567",
            "Test Artist",
            "Test Track",
            "BP001",
        ),
    )
    conn.commit()
    yield conn
    conn.close()


def test_known_isrc_same_quality_is_skipped(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intent = TrackIntent(isrc="USABC1234567", bit_depth=16, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert manifest.skip_count == 1
    assert manifest.download_count == 0


def test_known_isrc_better_quality_is_upgrade(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    # 24bit offer = rank 3, current is rank 4 -> upgrade
    intent = TrackIntent(isrc="USABC1234567", bit_depth=24, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert len(manifest.upgrades) == 1
    assert manifest.download_count == 1


def test_unknown_track_is_new(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intent = TrackIntent(isrc="UNKNOWN9999999", bit_depth=16, sample_rate=44100, bitrate=0)
    manifest = resolver.resolve([intent])
    assert len(manifest.new) == 1


def test_manifest_summary_string(db_with_track):
    resolver = PreFlightResolver(db_with_track)
    intents = [
        TrackIntent(isrc="USABC1234567", bit_depth=16, sample_rate=44100, bitrate=0),  # skip
        TrackIntent(isrc="NEW001", bit_depth=24, sample_rate=96000, bitrate=0),  # new
    ]
    manifest = resolver.resolve(intents)
    summary = manifest.summary()
    assert "1 new" in summary
    assert "1 skipped" in summary
