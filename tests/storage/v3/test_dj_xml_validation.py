from __future__ import annotations

import hashlib
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from tagslut.dj.admission import admit_track
from tagslut.dj.xml_emit import emit_rekordbox_xml
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    return conn


def _insert_identity(conn: sqlite3.Connection, *, title: str, artist: str, isrc: str) -> int:
    cur = conn.execute(
        f"INSERT INTO track_identity (title_norm, artist_norm, isrc, identity_key{PROV_COLS})"
        f" VALUES (?, ?, ?, ?{PROV_VALS})",
        (title, artist, isrc, isrc),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_asset_and_mp3(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    isrc: str,
    mp3_path: Path,
) -> int:
    asset_cur = conn.execute(
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)",
        (f"/library/{isrc}.flac",),
    )
    asset_id = asset_cur.lastrowid
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence) VALUES (?, ?, 1.0)",
        (identity_id, asset_id),
    )
    mp3_cur = conn.execute(
        """
        INSERT INTO mp3_asset
          (identity_id, asset_id, profile, path, status, bitrate, transcoded_at)
        VALUES (?, ?, 'mp3_320_cbr', ?, 'verified', 320, datetime('now'))
        """,
        (identity_id, asset_id, str(mp3_path)),
    )
    conn.commit()
    return mp3_cur.lastrowid  # type: ignore[return-value]


def _admit_tracks(conn: sqlite3.Connection, tmp_path: Path, count: int) -> list[int]:
    admissions: list[int] = []
    for idx in range(count):
        isrc = f"ISRC-XML-{idx:03d}"
        identity_id = _insert_identity(
            conn,
            title=f"Title {idx}",
            artist=f"Artist {idx}",
            isrc=isrc,
        )
        mp3_id = _insert_asset_and_mp3(
            conn,
            identity_id=identity_id,
            isrc=isrc,
            mp3_path=tmp_path / "dj" / f"track_{idx}.mp3",
        )
        admissions.append(admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id))
    conn.commit()
    return admissions


def test_xml_has_dj_playlists_root(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _admit_tracks(conn, tmp_path, 1)

    out_xml = tmp_path / "root.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    root = ET.parse(str(out_xml)).getroot()
    assert root.tag == "DJ_PLAYLISTS"


def test_xml_track_ids_are_unique(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _admit_tracks(conn, tmp_path, 3)

    out_xml = tmp_path / "unique_ids.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    root = ET.parse(str(out_xml)).getroot()
    tracks = root.findall("COLLECTION/TRACK")
    track_ids = [track.attrib["TrackID"] for track in tracks]
    assert len(track_ids) == len(set(track_ids))


def test_xml_collection_entries_matches_track_count(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _admit_tracks(conn, tmp_path, 3)

    out_xml = tmp_path / "entries.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    root = ET.parse(str(out_xml)).getroot()
    collection = root.find("COLLECTION")
    tracks = root.findall("COLLECTION/TRACK")
    assert collection is not None
    assert int(collection.attrib["Entries"]) == len(tracks)


def test_xml_playlist_track_keys_resolve(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    admissions = _admit_tracks(conn, tmp_path, 2)

    playlist_id = conn.execute(
        "INSERT INTO dj_playlist (name, sort_key) VALUES (?, ?)",
        ("Test Playlist", "001"),
    ).lastrowid
    conn.execute(
        "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal) VALUES (?, ?, ?)",
        (playlist_id, admissions[0], 0),
    )
    conn.execute(
        "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal) VALUES (?, ?, ?)",
        (playlist_id, admissions[1], 1),
    )
    conn.commit()

    out_xml = tmp_path / "playlist_keys.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    root = ET.parse(str(out_xml)).getroot()
    collection_ids = {track.attrib["TrackID"] for track in root.findall("COLLECTION/TRACK")}
    playlist_keys = {track.attrib["Key"] for track in root.findall("PLAYLISTS/NODE/NODE/TRACK")}
    assert playlist_keys
    assert playlist_keys.issubset(collection_ids)


def test_xml_is_deterministic(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _admit_tracks(conn, tmp_path, 2)

    first_xml = tmp_path / "deterministic_1.xml"
    second_xml = tmp_path / "deterministic_2.xml"

    emit_rekordbox_xml(conn, output_path=first_xml, skip_validation=True)
    emit_rekordbox_xml(conn, output_path=second_xml, skip_validation=True)

    first_hash = hashlib.sha256(first_xml.read_bytes()).hexdigest()
    second_hash = hashlib.sha256(second_xml.read_bytes()).hexdigest()
    assert first_hash == second_hash


def test_xml_location_uses_file_uri(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _admit_tracks(conn, tmp_path, 1)

    out_xml = tmp_path / "location_uri.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    track = ET.parse(str(out_xml)).getroot().find("COLLECTION/TRACK")
    assert track is not None
    assert track.attrib["Location"].startswith("file://localhost")
