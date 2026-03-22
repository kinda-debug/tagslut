import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.models import GigSet, GigSetTrack
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_files_table_has_dj_columns(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(files)")}
    assert "dj_pool_path" in cols
    assert "quality_rank" in cols
    assert "rekordbox_id" in cols
    assert "last_exported_usb" in cols


def test_gig_sets_table_exists(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(gig_sets)")}
    assert "name" in cols
    assert "filter_expr" in cols
    assert "exported_at" in cols


def test_gigs_table_exists(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(gigs)")}
    assert "date" in cols
    assert "venue" in cols
    assert "track_count" in cols


def test_gig_set_tracks_table_exists(mem_db):
    cols = {row[1] for row in mem_db.execute("PRAGMA table_info(gig_set_tracks)")}
    assert "gig_set_id" in cols
    assert "mp3_path" in cols
    assert "usb_dest_path" in cols


def test_init_db_is_idempotent(mem_db):
    # Calling init_db twice must not raise
    init_db(mem_db)


def test_gig_set_track_path_coercion():
    _ = GigSet(name="Test Set")
    t = GigSetTrack(gig_set_id=1, file_path="/music/track.flac", mp3_path="/dj/track.mp3")
    assert isinstance(t.file_path, Path)
    assert isinstance(t.mp3_path, Path)
