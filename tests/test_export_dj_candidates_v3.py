"""Tests for scripts/dj/export_candidates_v3.py."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_export(*, db: Path, out: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/dj/export_candidates_v3.py",
        "--db",
        str(db),
        "--out",
        str(out),
    ]
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
                canonical_artist,
                canonical_title,
                canonical_album,
                canonical_genre,
                canonical_sub_genre,
                canonical_bpm,
                canonical_duration,
                canonical_key,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "id:alpha", "Alpha", "Tune", "Alpha EP", "House", "Deep", 124.0, 320.0, "8A", None),
                (2, "id:orphan", "Orphan", "Lost", "Lost EP", "Techno", "Peak", 122.0, 300.0, "9A", None),
                (
                    3,
                    "id:missing_bpm",
                    "No",
                    "BPM",
                    "Silent EP",
                    "Ambient",
                    "Drone",
                    None,
                    280.0,
                    "10A",
                    None,
                ),
                (
                    4,
                    "id:beta",
                    "beta",
                    "anthem",
                    "Beta EP",
                    "Techno",
                    "Peak",
                    126.0,
                    310.0,
                    "9A",
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
                (41, "/root/d.flac", 310.0, 44100, 16, "ok"),
            ],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11, 1.0, "{}", 1),
                (2, 21, 1.0, "{}", 1),
                (4, 41, 1.0, "{}", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, ?, '{}', 1)",
            [
                (1, "active"),
                (2, "orphan"),
                (3, "active"),
                (4, "active"),
            ],
        )
        conn.executemany(
            "INSERT INTO dj_track_profile (identity_id, set_role, rating, energy, dj_tags_json) VALUES (?, ?, ?, ?, ?)",
            [
                (1, "builder", 4, 7, '["groovy"]'),
                (4, "peak", 2, 5, '["hard"]'),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_scope_switches_views_and_rows(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out_active = tmp_path / "active.csv"
    proc_active = _run_export(db=db, out=out_active, extra_args=["--scope", "active"])
    assert proc_active.returncode == 0, f"STDOUT:\n{proc_active.stdout}\nSTDERR:\n{proc_active.stderr}"
    assert "view: v_dj_pool_candidates_active_v3" in proc_active.stdout
    rows_active = _read_csv(out_active)
    assert [row["identity_id"] for row in rows_active] == ["1", "4"]

    out_orphan = tmp_path / "orphan.csv"
    proc_orphan = _run_export(db=db, out=out_orphan, extra_args=["--scope", "active+orphan"])
    assert proc_orphan.returncode == 0, f"STDOUT:\n{proc_orphan.stdout}\nSTDERR:\n{proc_orphan.stderr}"
    assert "view: v_dj_pool_candidates_active_orphan_v3" in proc_orphan.stdout
    rows_orphan = _read_csv(out_orphan)
    assert [row["identity_id"] for row in rows_orphan] == ["1", "4", "2"]

    out_all = tmp_path / "all.csv"
    proc_all = _run_export(db=db, out=out_all, extra_args=["--scope", "all"])
    assert proc_all.returncode == 0, f"STDOUT:\n{proc_all.stdout}\nSTDERR:\n{proc_all.stderr}"
    assert "view: v_dj_pool_candidates_v3" in proc_all.stdout
    rows_all = _read_csv(out_all)
    assert [row["identity_id"] for row in rows_all] == ["1", "4", "3", "2"]


def test_operational_filters_apply(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out_filtered = tmp_path / "filtered.csv"
    proc_filtered = _run_export(
        db=db,
        out=out_filtered,
        extra_args=[
            "--scope",
            "all",
            "--only-profiled",
            "--min-rating",
            "3",
            "--min-energy",
            "6",
            "--key",
            "8A",
        ],
    )
    assert proc_filtered.returncode == 0, f"STDOUT:\n{proc_filtered.stdout}\nSTDERR:\n{proc_filtered.stderr}"
    rows_filtered = _read_csv(out_filtered)
    assert [row["identity_id"] for row in rows_filtered] == ["1"]


def test_min_bpm_strict_and_non_strict_behavior(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out_strict = tmp_path / "strict.csv"
    proc_strict = _run_export(
        db=db,
        out=out_strict,
        extra_args=["--scope", "all", "--min-bpm", "123", "--genre", "Ambient"],
    )
    assert proc_strict.returncode == 0, f"STDOUT:\n{proc_strict.stdout}\nSTDERR:\n{proc_strict.stderr}"
    rows_strict = _read_csv(out_strict)
    assert len(rows_strict) == 0

    out_non_strict = tmp_path / "non_strict.csv"
    proc_non_strict = _run_export(
        db=db,
        out=out_non_strict,
        extra_args=["--scope", "all", "--min-bpm", "123", "--genre", "Ambient", "--no-strict"],
    )
    assert proc_non_strict.returncode == 0, (
        f"STDOUT:\n{proc_non_strict.stdout}\nSTDERR:\n{proc_non_strict.stderr}"
    )
    rows_non_strict = _read_csv(out_non_strict)
    assert len(rows_non_strict) == 1
    assert '"missing_bpm":true' in rows_non_strict[0]["flags_json"]


def test_missing_view_returns_error(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP VIEW v_dj_pool_candidates_active_v3")
        conn.commit()
    finally:
        conn.close()

    out = tmp_path / "missing_view.csv"
    proc = _run_export(db=db, out=out, extra_args=["--scope", "active"])
    assert proc.returncode == 2
    assert "missing required view: v_dj_pool_candidates_active_v3" in proc.stdout
