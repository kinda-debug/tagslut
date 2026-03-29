from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tagslut.dj.admission import admit_track, validate_dj_library
from tagslut.dj.xml_emit import emit_rekordbox_xml
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


def _make_db(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.commit()
    return conn


def _insert_identity(
    conn: sqlite3.Connection,
    *,
    title: str,
    artist: str,
    isrc: str,
) -> int:
    cur = conn.execute(
        f"INSERT INTO track_identity (title_norm, artist_norm, isrc, identity_key{PROV_COLS})"
        f" VALUES (?, ?, ?, ?{PROV_VALS})",
        (title, artist, isrc, isrc),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_asset_linked_identity(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    flac_path: str,
) -> int:
    asset_cur = conn.execute(
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)",
        (flac_path,),
    )
    asset_id = asset_cur.lastrowid
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence) VALUES (?, ?, 1.0)",
        (identity_id, asset_id),
    )
    conn.commit()
    return int(asset_id)


def _insert_mp3_asset(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
    mp3_path: str,
    bitrate: int = 320,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO mp3_asset
          (identity_id, asset_id, profile, path, status, bitrate, transcoded_at)
        VALUES (?, ?, 'mp3_320_cbr', ?, 'verified', ?, datetime('now'))
        """,
        (identity_id, asset_id, mp3_path, bitrate),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_admitted_track(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    title: str,
    artist: str,
    isrc: str,
    with_file_metadata: bool,
) -> int:
    identity_id = _insert_identity(conn, title=title, artist=artist, isrc=isrc)
    asset_id = _insert_asset_linked_identity(
        conn,
        identity_id=identity_id,
        flac_path=f"/library/{isrc}.flac",
    )
    mp3_path = tmp_path / f"{isrc}.mp3"
    mp3_path.write_bytes(b"ok")
    mp3_id = _insert_mp3_asset(
        conn,
        identity_id=identity_id,
        asset_id=asset_id,
        mp3_path=str(mp3_path),
    )

    if with_file_metadata:
        conn.execute(
            """
            INSERT INTO files (path, isrc, bpm, key_camelot)
            VALUES (?, ?, ?, ?)
            """,
            (f"/masters/{isrc}.flac", isrc, 128.0, "8A"),
        )

    admission_id = admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()
    return admission_id


def test_emit_with_complete_metadata_succeeds(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _insert_admitted_track(
        conn,
        tmp_path,
        title="Complete Title",
        artist="Complete Artist",
        isrc="ISRC-COMPLETE-001",
        with_file_metadata=True,
    )

    out_xml = tmp_path / "rekordbox_complete.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    root = ET.parse(str(out_xml)).getroot()
    track = root.find("COLLECTION/TRACK")
    assert root.tag == "DJ_PLAYLISTS"
    assert track is not None
    assert track.attrib["Name"] == "Complete Title"
    assert track.attrib["Artist"] == "Complete Artist"
    assert track.attrib.get("AverageBpm") == "128.00"


def test_emit_with_missing_bpm_currently_succeeds(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _insert_admitted_track(
        conn,
        tmp_path,
        title="No BPM Title",
        artist="No BPM Artist",
        isrc="ISRC-NOBPM-001",
        with_file_metadata=False,
    )

    out_xml = tmp_path / "rekordbox_no_bpm.xml"

    # TODO: change to assert raises once enrichment gate is implemented.
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    track = ET.parse(str(out_xml)).getroot().find("COLLECTION/TRACK")
    assert track is not None
    assert "AverageBpm" not in track.attrib


def test_emit_with_missing_artist_title_blocked_by_validate(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _insert_admitted_track(
        conn,
        tmp_path,
        title="",
        artist="",
        isrc="ISRC-META-MISS-001",
        with_file_metadata=True,
    )

    report = validate_dj_library(conn)
    assert any(issue.kind == "MISSING_METADATA" for issue in report.issues)

    out_xml = tmp_path / "rekordbox_invalid_metadata.xml"
    with pytest.raises(ValueError, match="Pre-emit validation"):
        emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=False)


def test_validate_report_identifies_missing_metadata(tmp_path: Path) -> None:
    conn = _make_db(tmp_path)
    _insert_admitted_track(
        conn,
        tmp_path,
        title="Valid Title",
        artist="Valid Artist",
        isrc="ISRC-META-MISS-002",
        with_file_metadata=True,
    )

    conn.execute(
        "UPDATE track_identity SET artist_norm = '' WHERE isrc = ?",
        ("ISRC-META-MISS-002",),
    )
    conn.commit()

    report = validate_dj_library(conn)
    assert any(issue.kind == "MISSING_METADATA" for issue in report.issues)
