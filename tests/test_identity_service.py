"""Tests for the v3 identity service."""

from __future__ import annotations

import sqlite3

import pytest

from tagslut.storage.schema import init_db
from tagslut.storage.v3.identity_service import (
    link_asset_to_identity,
    mirror_identity_to_legacy,
    resolve_active_identity,
    resolve_or_create_identity,
)
from tagslut.storage.v3.schema import create_schema_v3


def _open_fixture_db(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "identity_service_v3.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    return conn


def _asset_row(conn: sqlite3.Connection, asset_id: int, path: str, duration_s: float = 300.0) -> sqlite3.Row:
    conn.execute(
        """
        INSERT INTO asset_file (id, path, duration_s)
        VALUES (?, ?, ?)
        """,
        (asset_id, path, duration_s),
    )
    row = conn.execute("SELECT * FROM asset_file WHERE id = ?", (asset_id,)).fetchone()
    assert row is not None
    return row


def test_resolve_active_identity_follows_two_hop_merge_chain(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                canonical_artist,
                canonical_title,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, "id:source", "Artist Source", "Track Source", None),
                (2, "id:middle", "Artist Middle", "Track Middle", None),
                (3, "id:active", "Artist Active", "Track Active", None),
            ],
        )
        conn.execute("UPDATE track_identity SET merged_into_id = 2 WHERE id = 1")
        conn.execute("UPDATE track_identity SET merged_into_id = 3 WHERE id = 2")

        resolved = resolve_active_identity(conn, 1)
    finally:
        conn.close()

    assert int(resolved["id"]) == 3
    assert str(resolved["identity_key"]) == "id:active"
    assert str(resolved["canonical_artist"]) == "Artist Active"
    assert str(resolved["canonical_title"]) == "Track Active"


def test_resolve_or_create_identity_uses_existing_active_asset_link(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 101, "/music/linked.flac")
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                canonical_artist,
                canonical_title,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, "id:linked-old", "Artist Old", "Track Old", None),
                (2, "id:linked-active", "Artist Active", "Track Active", None),
            ],
        )
        conn.execute("UPDATE track_identity SET merged_into_id = 2 WHERE id = 1")
        conn.execute(
            "INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active) VALUES (?, ?, ?, ?, ?)",
            (101, 1, 1.0, "existing", 1),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"isrc": "EXISTING-ISRC", "artist": "Ignored Artist", "title": "Ignored Title"},
            {"source": "test"},
        )
    finally:
        conn.close()

    assert identity_id == 2


def test_resolve_or_create_identity_matches_by_isrc(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 102, "/music/isrc.flac")
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, isrc, canonical_artist, canonical_title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (10, "id:isrc", "ISRC-123", "Artist A", "Track A"),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"isrc": "ISRC-123", "artist": "Artist A", "title": "Track A"},
            {"source": "test"},
        )
    finally:
        conn.close()

    assert identity_id == 10


def test_resolve_or_create_identity_matches_by_provider_id(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 103, "/music/provider.flac")
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, beatport_id, canonical_artist, canonical_title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (11, "beatport:BP-1", "BP-1", "Artist B", "Track B"),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"beatport_id": "BP-1", "artist": "Artist B", "title": "Track B"},
            {"source": "beatport"},
        )
    finally:
        conn.close()

    assert identity_id == 11


def test_resolve_or_create_identity_reuses_existing_identity_for_same_provider_id(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        _asset_row(conn, 201, "/music/a.flac", duration_s=300.0)
        _asset_row(conn, 202, "/music/b.flac", duration_s=300.0)
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, beatport_id, canonical_artist, canonical_title)
            VALUES (?, ?, ?, ?, ?)
            """,
            (30, "beatport:BP-123", "BP-123", "Artist A", "Track A"),
        )
        row_a = conn.execute("SELECT * FROM asset_file WHERE id = ?", (201,)).fetchone()
        row_b = conn.execute("SELECT * FROM asset_file WHERE id = ?", (202,)).fetchone()
        assert row_a is not None and row_b is not None

        first_id = resolve_or_create_identity(
            conn,
            row_a,
            {"beatport_id": "BP-123", "artist": "Artist A", "title": "Track A"},
            {"source": "beatport"},
        )
        second_id = resolve_or_create_identity(
            conn,
            row_b,
            {"beatport_id": "BP-123", "artist": "Artist A", "title": "Track A"},
            {"source": "beatport"},
        )
        count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()
    finally:
        conn.close()

    assert first_id == 30
    assert second_id == 30
    assert count is not None
    assert int(count[0]) == 1


def test_resolve_or_create_identity_merges_provider_ids_for_same_isrc(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 203, "/music/isrc-merge.flac", duration_s=300.0)
        conn.execute(
            """
            INSERT INTO track_identity (id, identity_key, isrc, beatport_id, canonical_artist, canonical_title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (31, "isrc:merge-1", "ISRC-MERGE-1", "BP-999", "Artist A", "Track A"),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"isrc": "ISRC-MERGE-1", "tidal_id": "TD-777", "artist": "Artist A", "title": "Track A"},
            {"source": "tidal"},
        )
        row = conn.execute("SELECT isrc, beatport_id, tidal_id FROM track_identity WHERE id = ?", (31,)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()
    finally:
        conn.close()

    assert identity_id == 31
    assert row is not None
    assert str(row["isrc"]) == "ISRC-MERGE-1"
    assert str(row["beatport_id"]) == "BP-999"
    assert str(row["tidal_id"]) == "TD-777"
    assert count is not None
    assert int(count[0]) == 1


def test_resolve_or_create_identity_matches_fuzzy_and_preserves_exact_fields(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 104, "/music/fuzzy.flac", duration_s=301.0)
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                beatport_id,
                isrc,
                artist_norm,
                title_norm,
                canonical_artist,
                canonical_title,
                canonical_duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                12,
                "text:artist c|track c",
                "BP-ORIG",
                None,
                "artist c",
                "track c",
                "Artist C",
                "Track C",
                300.0,
            ),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {
                "artist": "  Artist   C ",
                "title": "Track C",
                "duration": 301.0,
                "beatport_id": "BP-NEW",
                "isrc": "ISRC-FILL",
            },
            {"source": "test"},
        )
        row = conn.execute(
            "SELECT beatport_id, isrc FROM track_identity WHERE id = ?",
            (12,),
        ).fetchone()
    finally:
        conn.close()

    assert identity_id == 12
    assert row is not None
    assert str(row["beatport_id"]) == "BP-ORIG"
    assert str(row["isrc"]) == "ISRC-FILL"


def test_resolve_or_create_identity_matches_fuzzy_with_short_artist_prefix(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 109, "/music/short-prefix.flac", duration_s=180.0)
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                artist_norm,
                title_norm,
                canonical_artist,
                canonical_title,
                canonical_duration
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                13,
                "text:abc|track short",
                "abc",
                "track short",
                "ABC",
                "Track Short",
                180.0,
            ),
        )

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"artist": "ABC", "title": "Track Short", "duration": 180.0},
            {"source": "test"},
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM track_identity WHERE identity_key = ?",
            ("text:abc|track short",),
        ).fetchone()
    finally:
        conn.close()

    assert identity_id == 13
    assert count is not None
    assert int(count[0]) == 1


def test_resolve_or_create_identity_creates_new_identity_when_no_match_exists(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 105, "/music/new.flac", duration_s=250.0)

        identity_id = resolve_or_create_identity(
            conn,
            asset_row,
            {"artist": "Create Artist", "title": "Create Title", "duration": 250.0},
            {"source": "test"},
        )
        row = conn.execute(
            """
            SELECT identity_key, artist_norm, title_norm, canonical_artist, canonical_title, canonical_duration
            FROM track_identity
            WHERE id = ?
            """,
            (identity_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert str(row["identity_key"]) == "text:create artist|create title"
    assert str(row["artist_norm"]) == "create artist"
    assert str(row["title_norm"]) == "create title"
    assert str(row["canonical_artist"]) == "Create Artist"
    assert str(row["canonical_title"]) == "Create Title"
    assert float(row["canonical_duration"]) == 250.0


def test_resolve_or_create_identity_reuses_existing_identity_on_repeated_create_path(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        asset_row = _asset_row(conn, 108, "/music/retry.flac", duration_s=200.0)

        first_id = resolve_or_create_identity(conn, asset_row, {}, {})
        second_id = resolve_or_create_identity(conn, asset_row, {}, {})

        row = conn.execute(
            """
            SELECT id, identity_key
            FROM track_identity
            WHERE identity_key = ?
            """,
            ("unidentified:asset:108",),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM track_identity WHERE identity_key = ?",
            ("unidentified:asset:108",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert count is not None
    assert first_id == second_id
    assert int(row["id"]) == first_id
    assert str(row["identity_key"]) == "unidentified:asset:108"
    assert int(count[0]) == 1


def test_mirror_identity_to_legacy_keeps_files_and_library_tracks_in_parity(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        init_db(conn)
        asset_row = _asset_row(conn, 106, "/music/mirror.flac", duration_s=245.0)
        conn.execute("INSERT INTO files (path) VALUES (?)", (str(asset_row["path"]),))
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                isrc,
                canonical_title,
                canonical_artist,
                canonical_album,
                canonical_genre,
                canonical_sub_genre,
                canonical_label,
                canonical_catalog_number,
                canonical_mix_name,
                canonical_duration,
                canonical_year,
                canonical_release_date,
                canonical_bpm,
                canonical_key,
                ref_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                20,
                "isrc:mirror123",
                "MIRROR123",
                "Mirror Title",
                "Mirror Artist",
                "Mirror Album",
                "Mirror Genre",
                "Mirror Sub",
                "Mirror Label",
                "CAT-123",
                "Extended Mix",
                245.0,
                2024,
                "2024-08-01",
                128.5,
                "8A",
                "beatport",
            ),
        )
        conn.execute(
            "INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active) VALUES (?, ?, ?, ?, ?)",
            (106, 20, 1.0, "test", 1),
        )

        mirror_identity_to_legacy(conn, 20, 106)

        files_row = conn.execute(
            """
            SELECT
                library_track_key,
                canonical_title,
                canonical_artist,
                canonical_album,
                canonical_isrc,
                canonical_duration,
                canonical_duration_source,
                canonical_year,
                canonical_release_date,
                canonical_bpm,
                canonical_key,
                canonical_genre,
                canonical_sub_genre,
                canonical_label,
                canonical_catalog_number,
                canonical_mix_name
            FROM files
            WHERE path = ?
            """,
            (str(asset_row["path"]),),
        ).fetchone()
        identity_row = conn.execute(
            """
            SELECT
                identity_key,
                canonical_title,
                canonical_artist,
                canonical_album,
                isrc,
                canonical_duration,
                ref_source,
                canonical_year,
                canonical_release_date,
                canonical_bpm,
                canonical_key,
                canonical_genre,
                canonical_sub_genre,
                canonical_label,
                canonical_catalog_number,
                canonical_mix_name
            FROM track_identity
            WHERE id = 20
            """
        ).fetchone()
        library_track_row = conn.execute(
            """
            SELECT
                library_track_key,
                title,
                artist,
                album,
                duration_ms,
                isrc,
                release_date,
                genre,
                bpm,
                musical_key,
                label
            FROM library_tracks
            WHERE library_track_key = ?
            """,
            ("isrc:mirror123",),
        ).fetchone()
    finally:
        conn.close()

    assert files_row is not None
    assert identity_row is not None
    assert library_track_row is not None

    assert str(files_row["library_track_key"]) == str(identity_row["identity_key"])
    assert str(files_row["canonical_title"]) == str(identity_row["canonical_title"])
    assert str(files_row["canonical_artist"]) == str(identity_row["canonical_artist"])
    assert str(files_row["canonical_album"]) == str(identity_row["canonical_album"])
    assert str(files_row["canonical_isrc"]) == str(identity_row["isrc"])
    assert float(files_row["canonical_duration"]) == float(identity_row["canonical_duration"])
    assert str(files_row["canonical_duration_source"]) == str(identity_row["ref_source"])
    assert int(files_row["canonical_year"]) == int(identity_row["canonical_year"])
    assert str(files_row["canonical_release_date"]) == str(identity_row["canonical_release_date"])
    assert float(files_row["canonical_bpm"]) == float(identity_row["canonical_bpm"])
    assert str(files_row["canonical_key"]) == str(identity_row["canonical_key"])
    assert str(files_row["canonical_genre"]) == str(identity_row["canonical_genre"])
    assert str(files_row["canonical_sub_genre"]) == str(identity_row["canonical_sub_genre"])
    assert str(files_row["canonical_label"]) == str(identity_row["canonical_label"])
    assert str(files_row["canonical_catalog_number"]) == str(identity_row["canonical_catalog_number"])
    assert str(files_row["canonical_mix_name"]) == str(identity_row["canonical_mix_name"])

    assert str(library_track_row["library_track_key"]) == str(identity_row["identity_key"])
    assert str(library_track_row["title"]) == str(identity_row["canonical_title"])
    assert str(library_track_row["artist"]) == str(identity_row["canonical_artist"])
    assert str(library_track_row["album"]) == str(identity_row["canonical_album"])
    assert int(library_track_row["duration_ms"]) == 245000
    assert str(library_track_row["isrc"]) == str(identity_row["isrc"])
    assert str(library_track_row["release_date"]) == str(identity_row["canonical_release_date"])
    assert str(library_track_row["genre"]) == str(identity_row["canonical_genre"])
    assert float(library_track_row["bpm"]) == float(identity_row["canonical_bpm"])
    assert str(library_track_row["musical_key"]) == str(identity_row["canonical_key"])
    assert str(library_track_row["label"]) == str(identity_row["canonical_label"])


def test_mirror_identity_to_legacy_warns_when_files_has_no_canonical_columns(
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE)")
        asset_row = _asset_row(conn, 110, "/music/mirror-warning.flac", duration_s=210.0)
        conn.execute("INSERT INTO files (path) VALUES (?)", (str(asset_row["path"]),))
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                canonical_title,
                canonical_artist
            ) VALUES (?, ?, ?, ?)
            """,
            (21, "warning:test", "Warning Title", "Warning Artist"),
        )

        with caplog.at_level("WARNING", logger="tagslut.storage.v3.identity_service"):
            mirror_identity_to_legacy(conn, 21, 110)
    finally:
        conn.close()

    assert "no canonical_* columns found in 'files' table" in caplog.text
    assert "identity 21" in caplog.text


def test_link_asset_to_identity_upserts_single_active_row_per_asset(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        _asset_row(conn, 107, "/music/link-upsert.flac")
        conn.executemany(
            """
            INSERT INTO track_identity (id, identity_key)
            VALUES (?, ?)
            """,
            [
                (30, "id:first"),
                (31, "id:second"),
            ],
        )

        link_asset_to_identity(conn, 107, 30, 0.75, "first-pass")
        link_asset_to_identity(conn, 107, 31, 0.95, "second-pass")

        row = conn.execute(
            """
            SELECT asset_id, identity_id, confidence, link_source, active
            FROM asset_link
            WHERE asset_id = ?
            """,
            (107,),
        ).fetchone()
        count = conn.execute(
            "SELECT COUNT(*) FROM asset_link WHERE asset_id = ?",
            (107,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert count is not None
    assert int(count[0]) == 1
    assert int(row["asset_id"]) == 107
    assert int(row["identity_id"]) == 31
    assert float(row["confidence"]) == 0.95
    assert str(row["link_source"]) == "second-pass"
    assert int(row["active"]) == 1


def test_link_asset_to_identity_resolves_merged_identity_to_active_row(tmp_path) -> None:
    conn = _open_fixture_db(tmp_path)
    try:
        _asset_row(conn, 111, "/music/link-merged.flac")
        conn.executemany(
            """
            INSERT INTO track_identity (id, identity_key, merged_into_id)
            VALUES (?, ?, ?)
            """,
            [
                (40, "id:active", None),
                (41, "id:merged", 40),
            ],
        )

        link_asset_to_identity(conn, 111, 41, 0.85, "merge-test")

        row = conn.execute(
            "SELECT identity_id FROM asset_link WHERE asset_id = ?",
            (111,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row["identity_id"]) == 40
