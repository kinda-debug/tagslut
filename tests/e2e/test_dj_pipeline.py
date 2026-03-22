"""End-to-end DJ pipeline proofs.

Covers the five canonical E2E scenarios from the task specification:

  E2E-1: intake → mp3 build (dry-run: FLAC not on disk, verify count reported)
  E2E-2: existing inventory → mp3 reconcile (full reconcile flow)
  E2E-3: existing MP3 → dj admit / backfill (admit + validate passes)
  E2E-4: dj state → deterministic Rekordbox XML (byte-identical across two emits)
  E2E-5: XML patch integrity
         - new track added to playlist then patched: new track appears in XML
         - on-disk XML tampered before patch: fails loudly

All tests use SQLite + tmp_path fixtures only. No network, no DJ hardware.
DB assertions and file/manifest content are checked, not just return codes.
"""
from __future__ import annotations

import hashlib
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tagslut.dj.admission import admit_track, backfill_admissions, validate_dj_library
from tagslut.dj.xml_emit import emit_rekordbox_xml, patch_rekordbox_xml
from tagslut.exec.mp3_build import Mp3BuildResult, build_mp3_from_identity, reconcile_mp3_library
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _insert_asset_file(conn: sqlite3.Connection, *, path: str) -> int:
    cur = conn.execute(
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)", (path,)
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _insert_asset_link(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
) -> None:
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence) VALUES (?, ?, 1.0)",
        (identity_id, asset_id),
    )
    conn.commit()


def _insert_mp3_asset(
    conn: sqlite3.Connection,
    *,
    identity_id: int,
    asset_id: int,
    path: str,
    status: str = "verified",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO mp3_asset
          (identity_id, asset_id, profile, path, status, transcoded_at)
        VALUES (?, ?, 'mp3_320_cbr', ?, ?, datetime('now'))
        """,
        (identity_id, asset_id, path, status),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def _write_tagged_mp3(path: Path, *, title: str, artist: str, isrc: str = "") -> None:
    """Write an ID3-tagged stub so mutagen can read it."""
    from mutagen.id3 import ID3, TALB, TIT2, TPE1, TSRC

    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text="Test Album"))
    if isrc:
        tags.add(TSRC(encoding=3, text=isrc))
    tags.save(str(path))


def _create_playlist(
    conn: sqlite3.Connection,
    *,
    name: str,
    admission_ids: list[int],
) -> int:
    cur = conn.execute(
        "INSERT INTO dj_playlist (name) VALUES (?)", (name,)
    )
    pl_id = cur.lastrowid
    for ordinal, da_id in enumerate(admission_ids):
        conn.execute(
            "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal)"
            " VALUES (?, ?, ?)",
            (pl_id, da_id, ordinal),
        )
    conn.commit()
    return pl_id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# E2E-1: intake → mp3 build
# ---------------------------------------------------------------------------


def test_e2e1_mp3_build_dry_run_reports_count(tmp_path: Path) -> None:
    """Given canonical identities with FLAC assets on disk,
    build_mp3_from_identity(dry_run=True) reports the correct build count
    without writing any files or mp3_asset rows.
    """
    conn = _make_db(tmp_path)

    flac_files = []
    for n in range(3):
        flac = tmp_path / "library" / f"track_{n}.flac"
        flac.parent.mkdir(parents=True, exist_ok=True)
        flac.write_bytes(b"FLAC-stub")

        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist="Artist", isrc=f"ISRC-E1-{n}"
        )
        asset_id = _insert_asset_file(conn, path=str(flac))
        _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)
        flac_files.append(flac)

    dj_root = tmp_path / "dj"
    result: Mp3BuildResult = build_mp3_from_identity(conn, dj_root=dj_root, dry_run=True)

    assert result.built == 3, f"Expected 3 pending builds. Got: {result}"
    assert result.failed == 0

    # dry_run must not write mp3_asset rows or files
    count = conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0]
    assert count == 0
    assert not any(dj_root.rglob("*.mp3")) if dj_root.exists() else True


def test_e2e1_mp3_build_skips_missing_flac(tmp_path: Path) -> None:
    """build_mp3_from_identity reports failure for identities whose FLAC is missing."""
    conn = _make_db(tmp_path)

    identity_id = _insert_identity(conn, title="Ghost Track", artist="Artist", isrc="ISRC-GHOST")
    asset_id = _insert_asset_file(conn, path="/nonexistent/ghost.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    result = build_mp3_from_identity(conn, dj_root=tmp_path / "dj", dry_run=True)

    assert result.failed == 1
    assert any("FLAC not found" in e for e in result.errors)


# ---------------------------------------------------------------------------
# E2E-2: existing inventory → mp3 reconcile
# ---------------------------------------------------------------------------


def test_e2e2_reconcile_creates_mp3_asset_rows(tmp_path: Path) -> None:
    """Given MP3 files on disk with no mp3_asset rows,
    reconcile_mp3_library creates mp3_asset rows linked to the correct identities.
    Unmatched files are reported clearly.
    """
    conn = _make_db(tmp_path)
    dj_root = tmp_path / "dj"

    # Two matched tracks
    for n in range(2):
        identity_id = _insert_identity(
            conn, title=f"Matched {n}", artist="Artist", isrc=f"ISRC-MATCH-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/matched_{n}.flac")
        _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

        mp3 = dj_root / f"matched_{n}.mp3"
        _write_tagged_mp3(mp3, title=f"Matched {n}", artist="Artist", isrc=f"ISRC-MATCH-{n}")

    # One unmatched track (no identity in DB)
    orphan = dj_root / "orphan.mp3"
    _write_tagged_mp3(orphan, title="Nobody", artist="Unknown")

    result = reconcile_mp3_library(conn, mp3_root=dj_root, dry_run=False)

    assert result.linked == 2, f"Expected 2 linked. Got: {result}"
    assert result.unmatched == 1, f"Expected 1 unmatched. Got: {result}"
    assert result.skipped_existing == 0

    # mp3_asset rows must exist for matched tracks
    count = conn.execute(
        "SELECT COUNT(*) FROM mp3_asset WHERE status = 'verified'"
    ).fetchone()[0]
    assert count == 2

    # Unmatched file is reported in errors, not silently dropped
    assert any("Nobody" in e or "orphan" in e for e in result.errors), (
        f"Expected orphan.mp3 to appear in errors. Errors: {result.errors}"
    )


def test_e2e2_reconcile_skips_already_registered(tmp_path: Path) -> None:
    """reconcile_mp3_library skips files already in mp3_asset and reports them."""
    conn = _make_db(tmp_path)
    dj_root = tmp_path / "dj"

    identity_id = _insert_identity(conn, title="Known", artist="Artist", isrc="ISRC-KNOWN")
    asset_id = _insert_asset_file(conn, path="/lib/known.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    mp3 = dj_root / "known.mp3"
    _write_tagged_mp3(mp3, title="Known", artist="Artist", isrc="ISRC-KNOWN")
    _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3))

    result = reconcile_mp3_library(conn, mp3_root=dj_root, dry_run=False)

    assert result.skipped_existing == 1
    assert result.linked == 0


# ---------------------------------------------------------------------------
# E2E-3: existing MP3 → dj admit / backfill
# ---------------------------------------------------------------------------


def test_e2e3_backfill_then_validate_passes(tmp_path: Path) -> None:
    """Given mp3_asset rows with no dj_admission rows,
    backfill creates admissions, dj_track_id_map is populated on first emit,
    and validate_dj_library passes with no errors.
    """
    conn = _make_db(tmp_path)

    for n in range(3):
        mp3 = tmp_path / f"track_{n}.mp3"
        mp3.write_bytes(b"")  # file must exist for validate to pass

        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist=f"Artist {n}", isrc=f"ISRC-E3-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
        _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3)
        )

    admitted, skipped = backfill_admissions(conn)
    conn.commit()

    assert admitted == 3
    assert skipped == 0

    # All admitted rows must be admitted
    count = conn.execute(
        "SELECT COUNT(*) FROM dj_admission WHERE status = 'admitted'"
    ).fetchone()[0]
    assert count == 3

    # validate must pass
    report = validate_dj_library(conn)
    assert report.ok, f"Expected validate to pass after backfill. Got: {report.summary()}"


def test_e2e3_backfill_idempotent(tmp_path: Path) -> None:
    """Running backfill twice does not create duplicate admissions."""
    conn = _make_db(tmp_path)

    identity_id = _insert_identity(conn, title="Idem", artist="A", isrc="ISRC-IDEM")
    asset_id = _insert_asset_file(conn, path="/lib/idem.flac")
    (tmp_path / "idem.mp3").write_bytes(b"")
    _insert_mp3_asset(
        conn, identity_id=identity_id, asset_id=asset_id,
        path=str(tmp_path / "idem.mp3")
    )

    backfill_admissions(conn)
    conn.commit()
    backfill_admissions(conn)
    conn.commit()

    count = conn.execute(
        "SELECT COUNT(*) FROM dj_admission WHERE identity_id = ?", (identity_id,)
    ).fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# E2E-4: dj state → deterministic Rekordbox XML
# ---------------------------------------------------------------------------


def test_e2e4_xml_byte_identical_across_two_emits(tmp_path: Path) -> None:
    """Two emits from the same DB state produce byte-identical XML files.

    This pins the XML determinism requirement: same DB state → same output.
    """
    conn = _make_db(tmp_path)

    # Set up 3 admitted tracks
    for n in range(3):
        mp3 = tmp_path / f"track_{n}.mp3"
        mp3.write_bytes(b"")
        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist="Artist", isrc=f"ISRC-E4-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
        mp3_id = _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3)
        )
        admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    # First emit
    xml1 = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=xml1, skip_validation=True)

    # Second emit (TrackIDs already in dj_track_id_map)
    xml2 = tmp_path / "v2.xml"
    emit_rekordbox_xml(conn, output_path=xml2, skip_validation=True)

    assert xml1.read_bytes() == xml2.read_bytes(), (
        "Two emits from the same DB state must produce byte-identical XML. "
        f"Sizes: {len(xml1.read_bytes())} vs {len(xml2.read_bytes())}"
    )


def test_e2e4_xml_contains_all_admitted_tracks(tmp_path: Path) -> None:
    """emit_rekordbox_xml includes exactly all admitted admissions in COLLECTION."""
    conn = _make_db(tmp_path)

    da_ids = []
    for n in range(4):
        mp3 = tmp_path / f"track_{n}.mp3"
        mp3.write_bytes(b"")
        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist="Artist", isrc=f"ISRC-E4B-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
        mp3_id = _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3)
        )
        da_ids.append(admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id))
    conn.commit()

    # Reject one admission so it drops out of active export state
    conn.execute(
        "UPDATE dj_admission SET status = 'rejected' WHERE id = ?", (da_ids[-1],)
    )
    conn.commit()

    xml_path = tmp_path / "out.xml"
    emit_rekordbox_xml(conn, output_path=xml_path, skip_validation=True)

    tree = ET.parse(str(xml_path))
    tracks = tree.getroot().findall("COLLECTION/TRACK")
    assert len(tracks) == 3, (
        "COLLECTION must contain exactly the 3 admitted admissions, not the rejected one."
    )


def test_e2e4_manifest_hash_matches_file(tmp_path: Path) -> None:
    """The manifest_hash stored in dj_export_state must match the SHA-256 of the emitted file."""
    conn = _make_db(tmp_path)

    mp3 = tmp_path / "track.mp3"
    mp3.write_bytes(b"")
    identity_id = _insert_identity(conn, title="Track", artist="Artist", isrc="ISRC-HASH")
    asset_id = _insert_asset_file(conn, path="/lib/track.flac")
    mp3_id = _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3))
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()

    xml_path = tmp_path / "out.xml"
    returned_hash = emit_rekordbox_xml(conn, output_path=xml_path, skip_validation=True)

    stored_hash = conn.execute(
        "SELECT manifest_hash FROM dj_export_state ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]

    file_hash = hashlib.sha256(xml_path.read_bytes()).hexdigest()

    assert returned_hash == stored_hash == file_hash, (
        f"Hash mismatch: returned={returned_hash[:8]}, stored={stored_hash[:8]}, file={file_hash[:8]}"
    )


# ---------------------------------------------------------------------------
# E2E-5: XML patch integrity
# ---------------------------------------------------------------------------


def _setup_two_admitted_tracks(
    tmp_path: Path, conn: sqlite3.Connection
) -> tuple[int, int]:
    """Insert two admitted tracks. Returns (da_id_1, da_id_2)."""
    da_ids = []
    for n in range(2):
        mp3 = tmp_path / f"track_{n}.mp3"
        mp3.write_bytes(b"")
        identity_id = _insert_identity(
            conn, title=f"Track {n}", artist=f"Artist {n}", isrc=f"ISRC-E5-{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
        mp3_id = _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3)
        )
        da_ids.append(admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id))
    conn.commit()
    return tuple(da_ids)  # type: ignore[return-value]


def test_e2e5_patch_adds_new_playlist_track(tmp_path: Path) -> None:
    """patch_rekordbox_xml includes a newly added playlist track.

    Scenario:
    1. Emit XML with 2 tracks in a playlist.
    2. Add a third admitted track to the playlist.
    3. Patch XML.
    4. Assert patched XML contains 3 tracks in the playlist.
    5. TrackIDs for original 2 tracks are unchanged.
    """
    conn = _make_db(tmp_path)
    da_id_0, da_id_1 = _setup_two_admitted_tracks(tmp_path, conn)

    # Create playlist with first two tracks
    pl_id = _create_playlist(conn, name="Test Playlist", admission_ids=[da_id_0, da_id_1])

    xml_v1 = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=xml_v1, skip_validation=True)

    # Capture original TrackIDs
    orig_ids = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT dj_admission_id, rekordbox_track_id FROM dj_track_id_map"
        ).fetchall()
    }

    # Add a third track
    mp3_new = tmp_path / "new_track.mp3"
    mp3_new.write_bytes(b"")
    identity_new = _insert_identity(
        conn, title="New Track", artist="New Artist", isrc="ISRC-E5-NEW"
    )
    asset_new = _insert_asset_file(conn, path="/lib/new_track.flac")
    mp3_id_new = _insert_mp3_asset(
        conn, identity_id=identity_new, asset_id=asset_new, path=str(mp3_new)
    )
    da_id_new = admit_track(conn, identity_id=identity_new, mp3_asset_id=mp3_id_new)

    # Add new track to playlist
    conn.execute(
        "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal) VALUES (?, ?, 2)",
        (pl_id, da_id_new),
    )
    conn.commit()

    xml_v2 = tmp_path / "v2.xml"
    patch_rekordbox_xml(conn, output_path=xml_v2, skip_validation=True)

    # Patched XML must contain 3 tracks in the playlist
    tree = ET.parse(str(xml_v2))
    root = tree.getroot()
    playlist_node = root.find("PLAYLISTS/NODE/NODE[@Name='Test Playlist']")
    assert playlist_node is not None, "Playlist 'Test Playlist' must appear in patched XML"
    assert len(playlist_node.findall("TRACK")) == 3, (
        "Patched playlist must contain 3 tracks (2 original + 1 new)"
    )

    # COLLECTION must have all 3 tracks
    collection_tracks = root.findall("COLLECTION/TRACK")
    assert len(collection_tracks) == 3

    # Original TrackIDs must be unchanged
    for da_id, orig_track_id in orig_ids.items():
        current_id = conn.execute(
            "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
            (da_id,),
        ).fetchone()[0]
        assert current_id == orig_track_id, (
            f"TrackID for admission {da_id} changed: {orig_track_id} → {current_id}"
        )


def test_e2e5_patch_fails_on_tampered_xml(tmp_path: Path) -> None:
    """patch_rekordbox_xml fails loudly when the prior XML file has been modified."""
    conn = _make_db(tmp_path)
    da_id_0, _ = _setup_two_admitted_tracks(tmp_path, conn)

    xml_path = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=xml_path, skip_validation=True)

    # Tamper: overwrite with different content
    xml_path.write_bytes(b"<tampered/>")

    with pytest.raises(ValueError, match="does not match stored manifest hash"):
        patch_rekordbox_xml(conn, output_path=tmp_path / "v2.xml", skip_validation=True)


def test_e2e5_patch_fails_with_no_prior_export(tmp_path: Path) -> None:
    """patch_rekordbox_xml fails loudly when no prior dj_export_state row exists."""
    conn = _make_db(tmp_path)
    da_id_0, _ = _setup_two_admitted_tracks(tmp_path, conn)

    with pytest.raises(ValueError, match="No prior Rekordbox XML export"):
        patch_rekordbox_xml(conn, output_path=tmp_path / "v2.xml", skip_validation=True)


def test_e2e5_patch_track_ids_stable_across_cycles(tmp_path: Path) -> None:
    """TrackIDs are stable across multiple emit → patch → patch cycles."""
    conn = _make_db(tmp_path)
    da_id_0, da_id_1 = _setup_two_admitted_tracks(tmp_path, conn)

    xml_v1 = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=xml_v1, skip_validation=True)

    id0_after_emit = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id_0,),
    ).fetchone()[0]

    for cycle in range(3):
        out = tmp_path / f"v{cycle + 2}.xml"
        patch_rekordbox_xml(conn, output_path=out, skip_validation=True)

    id0_final = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id_0,),
    ).fetchone()[0]

    assert id0_after_emit == id0_final, (
        f"TrackID for admission {da_id_0} must be stable across patch cycles: "
        f"{id0_after_emit} → {id0_final}"
    )
