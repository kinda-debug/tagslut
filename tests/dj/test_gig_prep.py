from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.dj.key_utils import compatible_keys
from tagslut.storage.schema import init_db


def _create_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "inventory.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    conn.close()
    return db_path


def _insert_file(
    db_path: Path,
    *,
    path: str,
    checksum: str,
    artist: str,
    title: str,
    bpm: float,
    key_camelot: str | None = None,
    canonical_key: str | None = None,
    genre: str | None = None,
    dj_set_role: str | None = None,
    dj_subrole: str | None = None,
    energy: int | None = None,
    dj_flag: int = 1,
    is_dj_material: int = 0,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO files (
            path,
            checksum,
            metadata_json,
            canonical_artist,
            canonical_title,
            bpm,
            key_camelot,
            canonical_key,
            canonical_genre,
            dj_set_role,
            dj_subrole,
            energy,
            dj_flag,
            is_dj_material
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            checksum,
            "{}",
            artist,
            title,
            bpm,
            key_camelot,
            canonical_key,
            genre,
            dj_set_role,
            dj_subrole,
            energy,
            dj_flag,
            is_dj_material,
        ),
    )
    conn.commit()
    conn.close()


def _run_gig_prep(db_path: Path, *args: str) -> str:
    result = CliRunner().invoke(
        cli,
        ["dj", "gig-prep", "--date", "2026-03-11", "--db", str(db_path), *args],
    )
    assert result.exit_code == 0, result.output
    return result.output


def _section_block(output: str, section_name: str) -> str:
    marker = f"── {section_name}"
    start = output.index(marker)
    remainder = output[start:]
    parts = remainder.split("\n\n", 1)
    return parts[0]


def test_gig_prep_groups_by_role(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/groove.flac",
        checksum="1",
        artist="A",
        title="Groove",
        bpm=108,
        key_camelot="6A",
        genre="House",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/prime.flac",
        checksum="2",
        artist="B",
        title="Prime",
        bpm=112,
        key_camelot="8B",
        genre="Techno",
        dj_set_role="prime",
    )
    _insert_file(
        db_path,
        path="/music/bridge.flac",
        checksum="3",
        artist="C",
        title="Bridge",
        bpm=118,
        key_camelot="9A",
        genre="Disco",
        dj_set_role="bridge",
    )
    _insert_file(
        db_path,
        path="/music/club.flac",
        checksum="4",
        artist="D",
        title="Club",
        bpm=124,
        key_camelot="10A",
        genre="Techno",
        dj_set_role="club",
    )
    _insert_file(
        db_path,
        path="/music/unassigned.flac",
        checksum="5",
        artist="E",
        title="Loose",
        bpm=120,
        key_camelot="11B",
        genre="House",
        dj_set_role=None,
    )

    output = _run_gig_prep(db_path)

    groove_index = output.index("── GROOVE")
    prime_index = output.index("── PRIME")
    bridge_index = output.index("── BRIDGE")
    club_index = output.index("── CLUB")
    unassigned_index = output.index("── _UNASSIGNED")
    assert groove_index < prime_index < bridge_index < club_index < unassigned_index
    assert "E – Loose" in _section_block(output, "_UNASSIGNED")
    assert "Keys: 6A×1" in _section_block(output, "GROOVE")


def test_gig_prep_bpm_filter(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/in.flac",
        checksum="1",
        artist="A",
        title="In",
        bpm=110,
        key_camelot="6A",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/out.flac",
        checksum="2",
        artist="B",
        title="Out",
        bpm=132,
        key_camelot="7A",
        dj_set_role="prime",
    )

    output = _run_gig_prep(db_path, "--bpm-min", "105", "--bpm-max", "120")

    assert "A – In" in output
    assert "B – Out" not in output


def test_gig_prep_roles_filter(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/groove.flac",
        checksum="1",
        artist="A",
        title="Groove",
        bpm=108,
        key_camelot="6A",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/prime.flac",
        checksum="2",
        artist="B",
        title="Prime",
        bpm=112,
        key_camelot="8B",
        dj_set_role="prime",
    )
    _insert_file(
        db_path,
        path="/music/bridge.flac",
        checksum="3",
        artist="C",
        title="Bridge",
        bpm=118,
        key_camelot="9A",
        dj_set_role="bridge",
    )
    _insert_file(
        db_path,
        path="/music/club.flac",
        checksum="4",
        artist="D",
        title="Club",
        bpm=124,
        key_camelot="10A",
        dj_set_role="club",
    )
    _insert_file(
        db_path,
        path="/music/unassigned.flac",
        checksum="5",
        artist="E",
        title="Loose",
        bpm=120,
        key_camelot="11B",
        dj_set_role=None,
    )

    output = _run_gig_prep(db_path, "--roles", "groove,prime")

    assert "── GROOVE" in output
    assert "── PRIME" in output
    assert "── BRIDGE" not in output
    assert "── CLUB" not in output
    assert "── _UNASSIGNED" in output


def test_gig_prep_sort_order(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/z.flac",
        checksum="1",
        artist="Zulu",
        title="Late",
        bpm=104,
        key_camelot="6A",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="2",
        artist="Alpha",
        title="Same BPM",
        bpm=104,
        key_camelot="7A",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="3",
        artist="Beta",
        title="Lower BPM",
        bpm=102,
        key_camelot="8A",
        dj_set_role="groove",
    )

    output = _run_gig_prep(db_path)
    groove_block = _section_block(output, "GROOVE")
    lines = [line for line in groove_block.splitlines() if " – " in line]

    assert lines == [
        "102  8A   Beta – Lower BPM",
        "104  7A   Alpha – Same BPM",
        "104  6A   Zulu – Late",
    ]


def test_gig_prep_csv_output(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="1",
        artist="Artist A",
        title="Track A",
        bpm=108,
        key_camelot="6A",
        canonical_key="C minor",
        genre="House",
        dj_set_role="groove",
        dj_subrole="opener",
        energy=5,
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="2",
        artist="Artist B",
        title="Track B",
        bpm=112,
        key_camelot="8B",
        canonical_key="C major",
        genre="Techno",
        dj_set_role=None,
        is_dj_material=1,
    )

    output = _run_gig_prep(db_path, "--format", "csv")
    reader = csv.DictReader(io.StringIO(output))
    rows = list(reader)

    assert reader.fieldnames == [
        "role",
        "subrole",
        "bpm",
        "key_camelot",
        "canonical_key",
        "artist",
        "title",
        "genre",
        "path",
        "energy",
        "dj_flag",
        "is_dj_material",
    ]
    assert len(rows) == 2
    assert rows[0]["role"] == "groove"
    assert rows[1]["role"] == "_unassigned"


def test_gig_prep_json_output(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="1",
        artist="Artist A",
        title="Track A",
        bpm=108,
        key_camelot="6A",
        canonical_key="C minor",
        genre="House",
        dj_set_role="groove",
        energy=5,
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="2",
        artist="Artist B",
        title="Track B",
        bpm=112,
        key_camelot=None,
        canonical_key="G major",
        genre="Techno",
        dj_set_role=None,
    )

    output = _run_gig_prep(db_path, "--format", "json")
    payload = json.loads(output)

    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["role"] == "groove"
    assert payload[1]["role"] == "_unassigned"
    assert payload[1]["key_camelot"] == "9B"
    assert payload[1]["canonical_key"] == "G major"


def test_gig_prep_records_gig(tmp_path: Path) -> None:
    db_path = _create_db(tmp_path)
    _insert_file(
        db_path,
        path="/music/a.flac",
        checksum="1",
        artist="Artist A",
        title="Track A",
        bpm=108,
        key_camelot="6A",
        dj_set_role="groove",
    )
    _insert_file(
        db_path,
        path="/music/b.flac",
        checksum="2",
        artist="Artist B",
        title="Track B",
        bpm=112,
        key_camelot="8B",
        dj_set_role=None,
    )

    _ = _run_gig_prep(db_path, "--venue", "The Club")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT date, venue, bpm_min, bpm_max, track_count FROM gigs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "2026-03-11"
    assert row[1] == "The Club"
    assert row[2] == 98
    assert row[3] == 130
    assert row[4] == 2


def test_compatible_keys() -> None:
    assert compatible_keys("8A") == ["7A", "8A", "9A", "8B"]
    assert compatible_keys("1B") == ["12B", "1B", "2B", "1A"]
    assert compatible_keys(None) == []
    assert compatible_keys("bad") == []
