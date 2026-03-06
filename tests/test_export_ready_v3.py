"""Tests for scripts/dj/export_ready_v3.py."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.dj_profile import ensure_schema
from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        ensure_schema(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                canonical_artist,
                canonical_title,
                canonical_bpm,
                canonical_key,
                canonical_genre,
                canonical_duration,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "id:a", "Alpha", "Tune", 124.0, "8A", "House", 320.0, None),
                (2, "id:b", "Beta", "Peak", 128.0, "9A", "Techno", 300.0, None),
            ],
        )
        conn.executemany(
            (
                "INSERT INTO asset_file "
                "(id, path, duration_s, sample_rate, bit_depth, integrity_state) VALUES (?, ?, ?, ?, ?, ?)"
            ),
            [
                (11, "/root/a.flac", 320.0, 44100, 16, "ok"),
                (21, "/root/b.flac", 300.0, 48000, 24, "ok"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [(11, 1), (21, 2)],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [(1, 11, 1.0, "{}", 1), (2, 21, 1.0, "{}", 1)],
        )
        conn.executemany(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, 'active', '{}', 1)",
            [(1,), (2,)],
        )
        conn.execute(
            """
            INSERT INTO dj_track_profile (identity_id, rating, energy, set_role, dj_tags_json, notes)
            VALUES (1, 4, 7, 'builder', '["groovy"]', 'set A')
            """
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_export_ready_includes_dj_fields(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    out = tmp_path / "ready.csv"
    cmd = [
        sys.executable,
        "scripts/dj/export_ready_v3.py",
        "--db",
        str(db),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_rows(out)
    row_one = next(row for row in rows if row["identity_id"] == "1")
    assert row_one["rating"] == "4"
    assert row_one["energy"] == "7"
    assert row_one["set_role"] == "builder"
    assert row_one["dj_tags_json"] == '["groovy"]'


def test_export_ready_filters_work(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    out = tmp_path / "filtered.csv"
    cmd = [
        sys.executable,
        "scripts/dj/export_ready_v3.py",
        "--db",
        str(db),
        "--out",
        str(out),
        "--min-rating",
        "4",
        "--set-role",
        "builder",
        "--only-profiled",
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_rows(out)
    assert len(rows) == 1
    assert rows[0]["identity_id"] == "1"
