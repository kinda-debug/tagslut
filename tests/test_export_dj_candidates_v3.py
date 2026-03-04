"""Tests for scripts/dj/export_candidates_v3.py."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.db.v3.schema import create_schema_v3

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
                id, identity_key, canonical_artist, canonical_title, canonical_bpm, canonical_duration, merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "id:alpha", "Alpha", "Tune", 124.0, 320.0, None),
                (2, "id:orphan", "Orphan", "Lost", 122.0, 300.0, None),
                (3, "id:missing_bpm", "No", "BPM", None, 280.0, None),
                (4, "id:beta", "beta", "anthem", 126.0, 310.0, None),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_file (id, path, duration_s, sample_rate, bit_depth, integrity_state) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (11, "/root/a.flac", 320.0, 44100, 16, "ok"),
                (31, "/root/c.flac", 280.0, 48000, 24, "ok"),
                (41, "/root/d.flac", 310.0, 44100, 16, "ok"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (11, 1),
                (31, 3),
                (41, 4),
            ],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11, 1.0, "{}", 1),
                (3, 31, 1.0, "{}", 1),
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
        conn.commit()
    finally:
        conn.close()
    return db


def test_active_identity_with_preferred_asset_exports_row(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    out = tmp_path / "candidates.csv"

    proc = _run_export(db=db, out=out)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    rows = _read_csv(out)
    alpha = next((row for row in rows if row["identity_id"] == "1"), None)
    assert alpha is not None
    assert alpha["preferred_asset_id"] == "11"
    assert alpha["preferred_path"] == "/root/a.flac"


def test_orphan_excluded_by_default_and_included_with_flag(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    out_default = tmp_path / "default.csv"
    proc_default = _run_export(db=db, out=out_default, extra_args=["--no-require-preferred"])
    assert proc_default.returncode == 0, f"STDOUT:\n{proc_default.stdout}\nSTDERR:\n{proc_default.stderr}"
    rows_default = _read_csv(out_default)
    assert all(row["identity_id"] != "2" for row in rows_default)

    out_with_orphans = tmp_path / "with_orphans.csv"
    proc_with_orphans = _run_export(
        db=db,
        out=out_with_orphans,
        extra_args=["--include-orphans", "--no-require-preferred"],
    )
    assert proc_with_orphans.returncode == 0, (
        f"STDOUT:\n{proc_with_orphans.stdout}\nSTDERR:\n{proc_with_orphans.stderr}"
    )
    rows_with_orphans = _read_csv(out_with_orphans)
    assert any(row["identity_id"] == "2" for row in rows_with_orphans)


def test_missing_preferred_asset_table_strict_and_non_required_modes(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("DROP TABLE preferred_asset")
        conn.commit()
    finally:
        conn.close()

    out_strict = tmp_path / "strict.csv"
    proc_strict = _run_export(db=db, out=out_strict)
    assert proc_strict.returncode == 2
    assert "missing required table: preferred_asset" in proc_strict.stdout

    out_non_required = tmp_path / "non_required.csv"
    proc_non_required = _run_export(db=db, out=out_non_required, extra_args=["--no-require-preferred"])
    assert proc_non_required.returncode == 0, (
        f"STDOUT:\n{proc_non_required.stdout}\nSTDERR:\n{proc_non_required.stderr}"
    )
    rows = _read_csv(out_non_required)
    assert len(rows) >= 1
    assert all(row["preferred_asset_id"] == "" for row in rows)
    assert all(row["preferred_path"] == "" for row in rows)


def test_min_bpm_filter_strict_and_non_strict_behavior(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)

    out_strict = tmp_path / "strict.csv"
    proc_strict = _run_export(
        db=db,
        out=out_strict,
        extra_args=["--min-bpm", "123", "--where", "artist='No'"],
    )
    assert proc_strict.returncode == 0, f"STDOUT:\n{proc_strict.stdout}\nSTDERR:\n{proc_strict.stderr}"
    rows_strict = _read_csv(out_strict)
    assert len(rows_strict) == 0

    out_non_strict = tmp_path / "non_strict.csv"
    proc_non_strict = _run_export(
        db=db,
        out=out_non_strict,
        extra_args=["--min-bpm", "123", "--where", "artist='No'", "--no-strict"],
    )
    assert proc_non_strict.returncode == 0, (
        f"STDOUT:\n{proc_non_strict.stdout}\nSTDERR:\n{proc_non_strict.stderr}"
    )
    rows_non_strict = _read_csv(out_non_strict)
    assert len(rows_non_strict) == 1
    assert '"missing_bpm":true' in rows_non_strict[0]["flags_json"]


def test_export_ordering_is_deterministic(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    out = tmp_path / "ordered.csv"

    proc = _run_export(db=db, out=out)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    rows = _read_csv(out)
    exported_ids = [row["identity_id"] for row in rows]
    assert exported_ids == ["1", "4", "3"]
