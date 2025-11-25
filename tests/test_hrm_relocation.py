from __future__ import annotations

import json
from pathlib import Path

import pytest

from dedupe import hrm_relocation, scanner, utils


def _init_scored_db(db_path: Path) -> None:
    ctx = utils.DatabaseContext(db_path)
    with ctx.connect() as connection:
        scanner.initialise_database(connection)
        for column in hrm_relocation.REQUIRED_SCORE_COLUMNS:
            connection.execute(f"ALTER TABLE library_files ADD COLUMN {column} REAL")
        connection.commit()


def test_missing_score_columns_raises(tmp_path: Path) -> None:
    db_path = tmp_path / "library.db"
    ctx = utils.DatabaseContext(db_path)
    with ctx.connect() as connection:
        scanner.initialise_database(connection)

    with pytest.raises(hrm_relocation.MissingScoreColumnsError):
        hrm_relocation.relocate_hrm(db_path=db_path, root=tmp_path, hrm_root=tmp_path)


def test_relocate_updates_manifest_and_db(tmp_path: Path) -> None:
    root = tmp_path / "library"
    hrm_root = tmp_path / "hrm"
    root.mkdir()
    hrm_root.mkdir()

    audio_path = root / "source.flac"
    audio_path.write_bytes(b"audio")

    db_path = tmp_path / "library.db"
    _init_scored_db(db_path)

    checksum = utils.compute_md5(audio_path)
    mtime = audio_path.stat().st_mtime
    tags = {
        "artist": "Test Artist",
        "album": "Test: Album",
        "title": "Example",
        "tracknumber": "2",
        "disctotal": "2",
        "discnumber": "1",
        "date": "2020-05-01",
    }

    ctx = utils.DatabaseContext(db_path)
    with ctx.connect() as connection:
        connection.execute(
            """
            INSERT INTO library_files (
                path, size_bytes, mtime, checksum, duration, sample_rate, bit_rate,
                channels, bit_depth, tags_json, fingerprint, fingerprint_duration,
                dup_group, duplicate_rank, is_canonical, score_integrity, score_audio,
                score_tags, score_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utils.normalise_path(str(audio_path)),
                audio_path.stat().st_size,
                mtime,
                checksum,
                None,
                None,
                None,
                None,
                None,
                json.dumps(tags),
                None,
                None,
                None,
                1,
                1,
                4.0,
                3.0,
                3.0,
                10.0,
            ),
        )
        connection.commit()

    stats = hrm_relocation.relocate_hrm(db_path=db_path, root=root, hrm_root=hrm_root, min_score=5)

    dest = (
        hrm_root
        / "Test Artist"
        / "(2020) Test꞉ Album"
        / "Test Artist - (2020) Test꞉ Album - 01-02. Example.flac"
    )
    manifest_path = Path("artifacts/manifests/hrm_relocation.tsv")

    assert stats.moved == 1
    assert stats.conflicts == 0
    assert stats.skipped == 0
    assert stats.missing == 0
    assert dest.exists()
    assert not audio_path.exists()

    with utils.DatabaseContext(db_path).connect() as connection:
        updated_path = connection.execute(
            "SELECT path FROM library_files WHERE checksum=?", (checksum,)
        ).fetchone()[0]
    assert Path(updated_path) == dest

    manifest_lines = manifest_path.read_text(encoding="utf8").strip().splitlines()
    assert manifest_lines[0] == "old_path\tnew_path\tchecksum\tscore_total\tresult"
    assert manifest_lines[1].endswith("\tmoved")

    manifest_path.unlink(missing_ok=True)
