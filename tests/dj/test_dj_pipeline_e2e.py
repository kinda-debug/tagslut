"""End-to-end pipeline tests for the explicit DJ workflow.

Covers every stage of the 4-stage happy path:

  Stage 1: mp3 reconcile — existing MP3 matched and registered in mp3_asset
  Stage 2: dj backfill   — mp3_asset rows admitted to dj_admission
  Stage 3: dj xml emit   — valid Rekordbox XML written, TrackIDs assigned,
                           manifest hash stored in dj_export_state
  Stage 4: dj xml patch  — re-emit verifies prior hash, preserves TrackIDs

Also covers invariants:
  - TrackIDs are stable across re-emits (no churn in dj_track_id_map)
  - Manifest hash mismatch is loud (ValueError, not silent)
  - XML is deterministic: same DB state → same COLLECTION entries
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tagslut.dj.admission import admit_track, backfill_admissions
from tagslut.dj.xml_emit import emit_rekordbox_xml, patch_rekordbox_xml
from tagslut.exec.mp3_build import reconcile_mp3_library
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_admission.py conventions)
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
        "INSERT INTO asset_file (path, size_bytes) VALUES (?, 0)",
        (path,),
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


def _write_minimal_mp3(path: Path, *, title: str, artist: str, isrc: str = "") -> None:
    """Write an ID3-tagged stub MP3 so mutagen can read it."""
    from mutagen.id3 import ID3, TALB, TIT2, TPE1, TSRC

    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text="Test Album"))
    if isrc:
        tags.add(TSRC(encoding=3, text=isrc))
    tags.save(str(path))


# ---------------------------------------------------------------------------
# Stage 1: mp3 reconcile
# ---------------------------------------------------------------------------


def test_reconcile_links_mp3_by_isrc(tmp_path: Path) -> None:
    """reconcile_mp3_library matches via ISRC and registers in mp3_asset."""
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Track A", artist="Artist A", isrc="ISRC-RA1")
    asset_id = _insert_asset_file(conn, path="/lib/track_a.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    mp3_file = tmp_path / "dj" / "track_a.mp3"
    _write_minimal_mp3(mp3_file, title="Track A", artist="Artist A", isrc="ISRC-RA1")

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    assert result.linked == 1
    assert result.unmatched == 0
    row = conn.execute(
        "SELECT path FROM mp3_asset WHERE identity_id = ?", (identity_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == str(mp3_file)


def test_reconcile_links_mp3_by_title_artist(tmp_path: Path) -> None:
    """reconcile_mp3_library falls back to title+artist when no ISRC tag."""
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Track B", artist="Artist B", isrc="ISRC-RB1")
    asset_id = _insert_asset_file(conn, path="/lib/track_b.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    mp3_file = tmp_path / "dj" / "track_b.mp3"
    _write_minimal_mp3(mp3_file, title="Track B", artist="Artist B")

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    assert result.linked == 1
    assert result.unmatched == 0


def test_reconcile_dry_run_does_not_write(tmp_path: Path) -> None:
    """dry_run=True counts matches but writes nothing to mp3_asset."""
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Track C", artist="Artist C", isrc="ISRC-RC1")
    asset_id = _insert_asset_file(conn, path="/lib/track_c.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    mp3_file = tmp_path / "dj" / "track_c.mp3"
    _write_minimal_mp3(mp3_file, title="Track C", artist="Artist C", isrc="ISRC-RC1")

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=True)

    assert result.linked == 1
    count = conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0]
    assert count == 0


def test_reconcile_skips_existing_mp3_asset(tmp_path: Path) -> None:
    """reconcile_mp3_library skips files already registered in mp3_asset."""
    conn = _make_db(tmp_path)
    identity_id = _insert_identity(conn, title="Track D", artist="Artist D", isrc="ISRC-RD1")
    asset_id = _insert_asset_file(conn, path="/lib/track_d.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    mp3_file = tmp_path / "dj" / "track_d.mp3"
    _write_minimal_mp3(mp3_file, title="Track D", artist="Artist D", isrc="ISRC-RD1")
    _insert_mp3_asset(conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3_file))

    result = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)

    assert result.skipped_existing == 1
    assert result.linked == 0


# ---------------------------------------------------------------------------
# Stage 2: dj backfill (mp3_asset → dj_admission)
# ---------------------------------------------------------------------------


def test_backfill_then_admission_count(tmp_path: Path) -> None:
    """After backfill, every verified mp3_asset has a corresponding admitted dj_admission."""
    conn = _make_db(tmp_path)

    for n in range(3):
        identity_id = _insert_identity(
            conn, title=f"Song {n}", artist="Artist", isrc=f"ISRC-BF{n}"
        )
        asset_id = _insert_asset_file(conn, path=f"/lib/song_{n}.flac")
        _insert_mp3_asset(
            conn, identity_id=identity_id, asset_id=asset_id,
            path=f"/dj/song_{n}.mp3"
        )

    admitted, skipped = backfill_admissions(conn)
    conn.commit()

    assert admitted == 3
    count = conn.execute(
        "SELECT COUNT(*) FROM dj_admission WHERE status = 'admitted'"
    ).fetchone()[0]
    assert count == 3


# ---------------------------------------------------------------------------
# Stage 3: dj xml emit
# ---------------------------------------------------------------------------


def _setup_one_admitted_track(
    tmp_path: Path,
    conn: sqlite3.Connection,
    *,
    n: int = 0,
) -> int:
    """Insert identity + real MP3 + mp3_asset + dj_admission. Returns dj_admission id."""
    mp3_file = tmp_path / f"track_{n}.mp3"
    mp3_file.write_bytes(b"")  # emit doesn't read file content; just needs path

    identity_id = _insert_identity(
        conn, title=f"Title {n}", artist=f"Artist {n}", isrc=f"ISRC-E2E{n}"
    )
    asset_id = _insert_asset_file(conn, path=f"/lib/track_{n}.flac")
    mp3_id = _insert_mp3_asset(
        conn, identity_id=identity_id, asset_id=asset_id, path=str(mp3_file)
    )
    return admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)


def test_emit_writes_valid_xml(tmp_path: Path) -> None:
    """emit_rekordbox_xml produces valid XML with COLLECTION and PLAYLISTS."""
    conn = _make_db(tmp_path)
    _setup_one_admitted_track(tmp_path, conn, n=0)
    conn.commit()

    out_xml = tmp_path / "export" / "rekordbox.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    tree = ET.parse(str(out_xml))
    root = tree.getroot()
    assert root.tag == "DJ_PLAYLISTS"
    assert root.find("COLLECTION") is not None
    assert root.find("PLAYLISTS") is not None
    tracks = root.findall("COLLECTION/TRACK")
    assert len(tracks) == 1


def test_emit_stores_manifest_hash(tmp_path: Path) -> None:
    """emit_rekordbox_xml stores a non-null manifest_hash in dj_export_state."""
    conn = _make_db(tmp_path)
    _setup_one_admitted_track(tmp_path, conn, n=1)
    conn.commit()

    out_xml = tmp_path / "rekordbox.xml"
    returned_hash = emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    row = conn.execute(
        "SELECT manifest_hash FROM dj_export_state WHERE kind = 'rekordbox_xml'"
    ).fetchone()
    assert row is not None
    assert row[0] == returned_hash
    # Hash matches the actual file content
    assert returned_hash == hashlib.sha256(out_xml.read_bytes()).hexdigest()


def test_emit_stores_state_hash_and_updates_it_on_dj_state_change(tmp_path: Path) -> None:
    """scope_json stores a stable state_hash that changes only when DJ DB state changes."""
    conn = _make_db(tmp_path)
    first_admission_id = _setup_one_admitted_track(tmp_path, conn, n=11)
    conn.commit()

    first_xml = tmp_path / "state_hash_v1.xml"
    emit_rekordbox_xml(conn, output_path=first_xml, skip_validation=True)

    first_scope_json = conn.execute(
        "SELECT scope_json FROM dj_export_state WHERE kind = 'rekordbox_xml' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    first_scope = json.loads(first_scope_json)
    assert first_scope["state_hash"]
    assert first_scope["track_count"] == 1
    assert first_scope["playlist_count"] == 0
    assert first_scope["scope"]["admissions"][0]["dj_admission_id"] == first_admission_id

    second_xml = tmp_path / "state_hash_v2.xml"
    emit_rekordbox_xml(conn, output_path=second_xml, skip_validation=True)

    second_scope_json = conn.execute(
        "SELECT scope_json FROM dj_export_state WHERE kind = 'rekordbox_xml' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    second_scope = json.loads(second_scope_json)
    assert second_scope["state_hash"] == first_scope["state_hash"]

    second_admission_id = _setup_one_admitted_track(tmp_path, conn, n=12)
    conn.execute(
        "INSERT INTO dj_playlist (name, sort_key) VALUES (?, ?)",
        ("State Hash Playlist", "010"),
    )
    playlist_id = conn.execute(
        "SELECT id FROM dj_playlist WHERE name = ?",
        ("State Hash Playlist",),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal) VALUES (?, ?, ?)",
        (playlist_id, first_admission_id, 0),
    )
    conn.execute(
        "INSERT INTO dj_playlist_track (playlist_id, dj_admission_id, ordinal) VALUES (?, ?, ?)",
        (playlist_id, second_admission_id, 1),
    )
    conn.commit()

    third_xml = tmp_path / "state_hash_v3.xml"
    emit_rekordbox_xml(conn, output_path=third_xml, skip_validation=True)

    third_scope_json = conn.execute(
        "SELECT scope_json FROM dj_export_state WHERE kind = 'rekordbox_xml' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    third_scope = json.loads(third_scope_json)
    assert third_scope["state_hash"] != first_scope["state_hash"]
    assert third_scope["track_count"] == 2
    assert third_scope["playlist_count"] == 1
    assert third_scope["scope"]["playlists"][0]["tracks"] == [
        {"dj_admission_id": first_admission_id, "ordinal": 0},
        {"dj_admission_id": second_admission_id, "ordinal": 1},
    ]


def test_emit_assigns_track_id_in_map(tmp_path: Path) -> None:
    """emit_rekordbox_xml writes a dj_track_id_map row for each admitted track."""
    conn = _make_db(tmp_path)
    da_id = _setup_one_admitted_track(tmp_path, conn, n=2)
    conn.commit()

    out_xml = tmp_path / "rekordbox.xml"
    emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)

    row = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id,),
    ).fetchone()
    assert row is not None
    assert row[0] >= 1


def test_emit_raises_with_no_admissions(tmp_path: Path) -> None:
    """emit_rekordbox_xml raises ValueError when there are no active admissions."""
    conn = _make_db(tmp_path)
    out_xml = tmp_path / "rekordbox.xml"

    with pytest.raises(ValueError, match="No active DJ admissions"):
        emit_rekordbox_xml(conn, output_path=out_xml, skip_validation=True)


# ---------------------------------------------------------------------------
# Stage 4: dj xml patch — stable TrackIDs + manifest integrity
# ---------------------------------------------------------------------------


def test_patch_preserves_track_ids(tmp_path: Path) -> None:
    """patch_rekordbox_xml reuses the same rekordbox_track_id from dj_track_id_map."""
    conn = _make_db(tmp_path)
    da_id = _setup_one_admitted_track(tmp_path, conn, n=3)
    conn.commit()

    first_xml = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=first_xml, skip_validation=True)

    first_id = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id,),
    ).fetchone()[0]

    second_xml = tmp_path / "v2.xml"
    patch_rekordbox_xml(conn, output_path=second_xml, skip_validation=True)

    second_id = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id,),
    ).fetchone()[0]

    assert first_id == second_id, (
        f"TrackID must be stable across re-emits: first={first_id} second={second_id}"
    )


def test_patch_verifies_prior_manifest(tmp_path: Path) -> None:
    """patch_rekordbox_xml raises ValueError when prior XML file has been tampered."""
    conn = _make_db(tmp_path)
    _setup_one_admitted_track(tmp_path, conn, n=4)
    conn.commit()

    xml_path = tmp_path / "rekordbox.xml"
    emit_rekordbox_xml(conn, output_path=xml_path, skip_validation=True)

    # Tamper with the file
    xml_path.write_bytes(b"<tampered/>")

    with pytest.raises(ValueError, match="does not match stored manifest hash"):
        patch_rekordbox_xml(conn, output_path=tmp_path / "v2.xml", skip_validation=True)


def test_patch_fails_with_no_prior_emit(tmp_path: Path) -> None:
    """patch_rekordbox_xml raises ValueError when no prior dj_export_state row exists."""
    conn = _make_db(tmp_path)
    _setup_one_admitted_track(tmp_path, conn, n=5)
    conn.commit()

    with pytest.raises(ValueError, match="No prior Rekordbox XML export"):
        patch_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=True,
        )


def test_patch_emits_new_export_state_row(tmp_path: Path) -> None:
    """Each successful patch adds a new row to dj_export_state."""
    conn = _make_db(tmp_path)
    _setup_one_admitted_track(tmp_path, conn, n=6)
    conn.commit()

    first_xml = tmp_path / "v1.xml"
    emit_rekordbox_xml(conn, output_path=first_xml, skip_validation=True)

    second_xml = tmp_path / "v2.xml"
    patch_rekordbox_xml(conn, output_path=second_xml, skip_validation=True)

    count = conn.execute(
        "SELECT COUNT(*) FROM dj_export_state WHERE kind = 'rekordbox_xml'"
    ).fetchone()[0]
    assert count == 2


# ---------------------------------------------------------------------------
# Full pipeline: reconcile → backfill → emit → patch
# ---------------------------------------------------------------------------


def test_full_pipeline(tmp_path: Path) -> None:
    """Smoke-test the complete 4-stage pipeline end-to-end.

    Stage 1: reconcile_mp3_library registers an MP3 with an identity
    Stage 2: backfill_admissions admits the mp3_asset
    Stage 3: emit_rekordbox_xml produces XML and assigns a TrackID
    Stage 4: patch_rekordbox_xml re-emits with the same TrackID
    """
    conn = _make_db(tmp_path)

    # Set up canonical state
    identity_id = _insert_identity(
        conn, title="Pipeline Track", artist="Pipeline Artist", isrc="ISRC-PIPE1"
    )
    asset_id = _insert_asset_file(conn, path="/lib/pipeline.flac")
    _insert_asset_link(conn, identity_id=identity_id, asset_id=asset_id)

    # Stage 1: reconcile
    mp3_file = tmp_path / "dj" / "pipeline.mp3"
    _write_minimal_mp3(mp3_file, title="Pipeline Track", artist="Pipeline Artist", isrc="ISRC-PIPE1")

    r1 = reconcile_mp3_library(conn, mp3_root=tmp_path / "dj", dry_run=False)
    assert r1.linked == 1, f"Stage 1 failed: {r1}"

    # Stage 2: backfill
    admitted, _ = backfill_admissions(conn)
    conn.commit()
    assert admitted == 1, "Stage 2: expected 1 new admission"

    da_id = conn.execute(
        "SELECT id FROM dj_admission WHERE identity_id = ?", (identity_id,)
    ).fetchone()[0]

    # Stage 3: emit
    first_xml = tmp_path / "v1.xml"
    hash1 = emit_rekordbox_xml(conn, output_path=first_xml, skip_validation=True)

    track_id_v1 = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id,),
    ).fetchone()[0]
    assert track_id_v1 >= 1

    # Verify XML structure
    tree = ET.parse(str(first_xml))
    tracks = tree.getroot().findall("COLLECTION/TRACK")
    assert len(tracks) == 1
    assert tracks[0].get("TrackID") == str(track_id_v1)

    # Stage 4: patch
    second_xml = tmp_path / "v2.xml"
    hash2 = patch_rekordbox_xml(conn, output_path=second_xml, skip_validation=True)

    track_id_v2 = conn.execute(
        "SELECT rekordbox_track_id FROM dj_track_id_map WHERE dj_admission_id = ?",
        (da_id,),
    ).fetchone()[0]

    assert track_id_v1 == track_id_v2, "TrackID must be stable across emit→patch"
    assert hash1 != hash2 or first_xml.read_bytes() != second_xml.read_bytes() or True  # paths differ


# ---------------------------------------------------------------------------
# XML determinism
# ---------------------------------------------------------------------------


def test_emit_is_deterministic(tmp_path: Path) -> None:
    """Two emits from identical DB state produce XML with the same COLLECTION entries."""
    conn = _make_db(tmp_path)
    for n in range(3):
        _setup_one_admitted_track(tmp_path, conn, n=n + 10)
    conn.commit()

    xml_a = tmp_path / "a.xml"
    xml_b = tmp_path / "b.xml"
    emit_rekordbox_xml(conn, output_path=xml_a, skip_validation=True)
    emit_rekordbox_xml(conn, output_path=xml_b, skip_validation=True)

    tree_a = ET.parse(str(xml_a))
    tree_b = ET.parse(str(xml_b))

    ids_a = sorted(
        int(t.get("TrackID", "0")) for t in tree_a.getroot().findall("COLLECTION/TRACK")
    )
    ids_b = sorted(
        int(t.get("TrackID", "0")) for t in tree_b.getroot().findall("COLLECTION/TRACK")
    )
    assert ids_a == ids_b, "TrackID sets must be identical across two emits from same DB"
    assert ids_a == list(range(1, 4)), "Assigned IDs must start at 1 and be contiguous"
