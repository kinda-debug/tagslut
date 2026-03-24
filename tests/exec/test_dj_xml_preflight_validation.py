from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from tagslut.dj.admission import (
    admit_track,
    record_validation_state,
    validate_dj_library,
)
from tagslut.dj.xml_emit import _build_export_scope, emit_rekordbox_xml
from tagslut.storage.schema import init_db
from tests.conftest import PROV_COLS, PROV_VALS

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "tagslut"
    / "storage"
    / "v3"
    / "migrations"
    / "0014_dj_validation_state.py"
)


def _load_migration_0014():
    spec = importlib.util.spec_from_file_location("migration_0014", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    _load_migration_0014().up(conn)
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


def _setup_admitted_track(
    conn: sqlite3.Connection,
    tmp_path: Path,
    *,
    suffix: str,
) -> int:
    mp3_file = tmp_path / f"track_{suffix}.mp3"
    mp3_file.write_bytes(b"")
    identity_id = _insert_identity(
        conn,
        title=f"Title {suffix}",
        artist=f"Artist {suffix}",
        isrc=f"ISRC-PREFLIGHT-{suffix}",
    )
    asset_id = _insert_asset_file(conn, path=f"/lib/track_{suffix}.flac")
    mp3_id = _insert_mp3_asset(
        conn,
        identity_id=identity_id,
        asset_id=asset_id,
        path=str(mp3_file),
    )
    admission_id = admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_id)
    conn.commit()
    return admission_id


def _record_pass_for_current_state(conn: sqlite3.Connection) -> str:
    _scope_payload, state_hash = _build_export_scope(conn, playlist_scope=None)
    record_validation_state(
        conn,
        state_hash=state_hash,
        issue_count=0,
        passed=True,
        summary="DJ library validation passed — no issues found.",
    )
    conn.commit()
    return state_hash


def test_emit_requires_prior_validate_pass(tmp_path: Path) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="needs_validate")

    with pytest.raises(ValueError, match="no passing 'dj validate' run"):
        emit_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=False,
        )


def test_emit_succeeds_after_validate_pass(tmp_path: Path) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="valid")
    _record_pass_for_current_state(conn)

    output_path = tmp_path / "rekordbox.xml"
    emit_rekordbox_xml(conn, output_path=output_path, skip_validation=False)

    assert output_path.exists()


def test_emit_fails_when_state_hash_stale(tmp_path: Path) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="stale")
    record_validation_state(
        conn,
        state_hash="not-the-current-state",
        issue_count=0,
        passed=True,
        summary="stale",
    )
    conn.commit()

    with pytest.raises(ValueError, match="no passing 'dj validate' run"):
        emit_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=False,
        )


def test_emit_with_skip_validation_bypasses_gate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="skip")

    output_path = tmp_path / "rekordbox.xml"
    emit_rekordbox_xml(conn, output_path=output_path, skip_validation=True)

    assert output_path.exists()
    captured = capsys.readouterr()
    assert (
        "WARNING: --skip-validation bypasses DJ library integrity checks. Use only for emergencies."
        in captured.err
    )


def test_validate_command_records_state_hash(tmp_path: Path) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="record")

    report = validate_dj_library(conn)
    assert report.ok

    _scope_payload, state_hash = _build_export_scope(conn, playlist_scope=None)
    record_validation_state(
        conn,
        state_hash=state_hash,
        issue_count=0,
        passed=True,
        summary=report.summary(),
    )
    conn.commit()

    row = conn.execute(
        "SELECT passed, state_hash FROM dj_validation_state ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] == state_hash


def test_emit_fails_when_admission_added_after_validate(tmp_path: Path) -> None:
    conn = _make_db()
    _setup_admitted_track(conn, tmp_path, suffix="before")
    _record_pass_for_current_state(conn)
    _setup_admitted_track(conn, tmp_path, suffix="after")

    with pytest.raises(ValueError, match="no passing 'dj validate' run"):
        emit_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=False,
        )


def test_emit_blocks_bad_mp3_status_even_if_validation_state_passed(tmp_path: Path) -> None:
    conn = _make_db()
    admission_id = _setup_admitted_track(conn, tmp_path, suffix="bad_status")

    mp3_asset_id = conn.execute(
        "SELECT mp3_asset_id FROM dj_admission WHERE id = ?",
        (admission_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE mp3_asset SET status = 'unverified' WHERE id = ?",
        (mp3_asset_id,),
    )
    conn.commit()

    _record_pass_for_current_state(conn)

    with pytest.raises(ValueError, match=r"(?s)Pre-emit validation failed:.*BAD_MP3_STATUS"):
        emit_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=False,
        )


def test_emit_blocks_duplicate_mp3_path_even_if_validation_state_passed(tmp_path: Path) -> None:
    conn = _make_db()
    admission_id = _setup_admitted_track(conn, tmp_path, suffix="dup_1")

    mp3_asset_id = conn.execute(
        "SELECT mp3_asset_id FROM dj_admission WHERE id = ?",
        (admission_id,),
    ).fetchone()[0]

    identity_id = _insert_identity(
        conn,
        title="Title dup_2",
        artist="Artist dup_2",
        isrc="ISRC-PREFLIGHT-dup_2",
    )
    _insert_asset_file(conn, path="/lib/track_dup_2.flac")
    admit_track(conn, identity_id=identity_id, mp3_asset_id=mp3_asset_id)
    conn.commit()

    _record_pass_for_current_state(conn)

    with pytest.raises(ValueError, match=r"(?s)Pre-emit validation failed:.*DUPLICATE_MP3_PATH"):
        emit_rekordbox_xml(
            conn,
            output_path=tmp_path / "rekordbox.xml",
            skip_validation=False,
        )
