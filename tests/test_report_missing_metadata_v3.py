"""Tests for scripts/dj/report_missing_metadata_v3.py."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_report(*, db: Path, out: Path | None, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/dj/report_missing_metadata_v3.py",
        "--db",
        str(db),
    ]
    if out is not None:
        cmd.extend(["--out", str(out)])
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_csv_with_header(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def _create_fixture_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                isrc,
                beatport_id,
                tidal_id,
                deezer_id,
                spotify_id,
                traxsource_id,
                musicbrainz_id,
                canonical_artist,
                canonical_title,
                canonical_album,
                canonical_genre,
                canonical_sub_genre,
                canonical_bpm,
                canonical_key,
                canonical_duration,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "id:alpha",
                    "ISRC1",
                    "BP1",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "Alpha",
                    "Tune",
                    "Alpha EP",
                    "House",
                    "Deep",
                    124.0,
                    "8A",
                    320.0,
                    None,
                ),
                (
                    2,
                    "id:beta",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "TS2",
                    None,
                    "Beta",
                    "Song",
                    "Beta EP",
                    "",
                    "",
                    None,
                    "",
                    300.0,
                    None,
                ),
                (
                    3,
                    "id:noartist",
                    None,
                    None,
                    None,
                    "DZ3",
                    None,
                    None,
                    None,
                    "",
                    "NoArtist",
                    "NoArtist EP",
                    "Techno",
                    "Peak",
                    120.0,
                    "9A",
                    310.0,
                    None,
                ),
                (
                    4,
                    "id:orphan",
                    None,
                    None,
                    "TD4",
                    None,
                    None,
                    None,
                    "MB4",
                    "Orphan",
                    "Lost",
                    "Lost EP",
                    "Trance",
                    "",
                    123.0,
                    "10A",
                    320.0,
                    None,
                ),
                (
                    5,
                    "id:nopref",
                    None,
                    None,
                    None,
                    None,
                    "SP5",
                    "TS5",
                    None,
                    "Gamma",
                    "NoPref",
                    "Gamma EP",
                    "House",
                    "",
                    128.0,
                    "11A",
                    330.0,
                    None,
                ),
            ],
        )
        conn.executemany(
            (
                "INSERT INTO asset_file "
                "(id, path, duration_s, sample_rate, bit_depth, integrity_state) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            [
                (11, "/root/a.flac", 320.0, 44100, 16, "ok"),
                (21, "/root/b.flac", 300.0, 44100, 16, "ok"),
                (31, "/root/c.flac", 310.0, 44100, 16, "ok"),
                (41, "/root/d.flac", 320.0, 44100, 16, "ok"),
            ],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11, 1.0, "{}", 1),
                (2, 21, 1.0, "{}", 1),
                (3, 31, 1.0, "{}", 1),
                (4, 41, 1.0, "{}", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, ?, '{}', 1)",
            [
                (1, "active"),
                (2, "active"),
                (3, "active"),
                (4, "orphan"),
                (5, "active"),
            ],
        )
        conn.executemany(
            "INSERT INTO dj_track_profile (identity_id, set_role, rating, energy, dj_tags_json) VALUES (?, ?, ?, ?, ?)",
            [
                (1, "builder", 4, 7, '["groovy"]'),
                (2, "peak", 2, 5, '["hard"]'),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_scope_selects_view_and_ordering(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out_active = tmp_path / "active.csv"
    proc_active = _run_report(db=db, out=out_active, extra_args=["--scope", "active"])
    assert proc_active.returncode == 0, f"STDOUT:\n{proc_active.stdout}\nSTDERR:\n{proc_active.stderr}"
    assert "view: v_dj_pool_candidates_active_v3" in proc_active.stdout
    rows_active = _read_csv(out_active)
    assert [row["identity_id"] for row in rows_active] == ["2", "3", "1"]

    out_orphan = tmp_path / "orphan.csv"
    proc_orphan = _run_report(db=db, out=out_orphan, extra_args=["--scope", "active+orphan"])
    assert proc_orphan.returncode == 0, f"STDOUT:\n{proc_orphan.stdout}\nSTDERR:\n{proc_orphan.stderr}"
    assert "view: v_dj_pool_candidates_active_orphan_v3" in proc_orphan.stdout
    rows_orphan = _read_csv(out_orphan)
    assert [row["identity_id"] for row in rows_orphan] == ["2", "3", "1", "4"]

    out_all = tmp_path / "all.csv"
    proc_all = _run_report(db=db, out=out_all, extra_args=["--scope", "all"])
    assert proc_all.returncode == 0, f"STDOUT:\n{proc_all.stdout}\nSTDERR:\n{proc_all.stderr}"
    assert "view: v_dj_pool_candidates_v3" in proc_all.stdout
    rows_all = _read_csv(out_all)
    assert [row["identity_id"] for row in rows_all] == ["2", "3", "1", "5", "4"]


def test_missing_flags_and_filters(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out = tmp_path / "flags.csv"
    proc = _run_report(
        db=db,
        out=out,
        extra_args=["--scope", "active", "--limit", "10"],
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_csv(out)
    row_beta = next(row for row in rows if row["identity_id"] == "2")
    assert row_beta["missing_bpm"] == "1"
    assert row_beta["missing_key"] == "1"
    assert row_beta["missing_genre"] == "1"
    assert row_beta["missing_core_fields"] == "0"
    assert row_beta["missing_strong_keys"] == "0"
    assert row_beta["most_missing_fields"] == "3"

    out_filtered = tmp_path / "filtered.csv"
    proc_filtered = _run_report(
        db=db,
        out=out_filtered,
        extra_args=["--scope", "all", "--only-profiled", "--min-rating", "3", "--min-energy", "6"],
    )
    assert proc_filtered.returncode == 0, f"STDOUT:\n{proc_filtered.stdout}\nSTDERR:\n{proc_filtered.stderr}"
    rows_filtered = _read_csv(out_filtered)
    assert [row["identity_id"] for row in rows_filtered] == ["1"]


def test_report_includes_deezer_fields(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out = tmp_path / "providers.csv"
    proc = _run_report(db=db, out=out, extra_args=["--scope", "active"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    fieldnames, rows = _read_csv_with_header(out)
    assert "deezer_id" in fieldnames
    assert "traxsource_id" in fieldnames
    assert "musicbrainz_id" in fieldnames
    assert "best_provider" in fieldnames
    assert "best_provider_id" in fieldnames
    assert "qobuz_id" not in fieldnames
    assert "missing_strong_keys" in fieldnames
    assert "qobuz" not in ",".join(fieldnames).lower()

    row_alpha = next(row for row in rows if row["identity_id"] == "1")
    assert row_alpha["deezer_id"] == ""
    assert row_alpha["missing_strong_keys"] == "0"
    assert row_alpha["best_provider"] == "beatport"

    row_noartist = next(row for row in rows if row["identity_id"] == "3")
    assert row_noartist["deezer_id"] == "DZ3"
    assert row_noartist["missing_strong_keys"] == "0"
    assert row_noartist["best_provider"] == "deezer"

    row_beta = next(row for row in rows if row["identity_id"] == "2")
    assert row_beta["best_provider"] == "traxsource"
    assert row_beta["best_provider_id"] == "TS2"
    assert "qobuz" not in ",".join(row_beta.values()).lower()


def test_provider_ladder_prefers_traxsource_over_spotify(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out = tmp_path / "ladder.csv"
    proc = _run_report(db=db, out=out, extra_args=["--scope", "all"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    rows = _read_csv(out)
    row_nopref = next(row for row in rows if row["identity_id"] == "5")
    assert row_nopref["best_provider"] == "traxsource"
    assert row_nopref["best_provider_id"] == "TS5"
    assert "qobuz" not in ",".join(row_nopref.values()).lower()


def test_missing_view_returns_error(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP VIEW v_dj_pool_candidates_active_v3")
        conn.commit()
    finally:
        conn.close()

    proc = _run_report(db=db, out=None, extra_args=["--scope", "active"])
    assert proc.returncode == 2
    assert "missing required view: v_dj_pool_candidates_active_v3" in proc.stdout
    assert 'hint: run "make apply-v3-schema V3=<db>" to install missing views' in proc.stdout
