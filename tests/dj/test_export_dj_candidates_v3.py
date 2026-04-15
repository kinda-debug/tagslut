"""Tests for scripts/dj/export_candidates_v3.py."""

from __future__ import annotations

import csv
import importlib.util
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_SCRIPT = PROJECT_ROOT / "scripts" / "dj" / "export_candidates_v3.py"


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


def _read_csv_with_header(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _load_export_module():
    spec = importlib.util.spec_from_file_location("export_candidates_v3", EXPORT_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
                canonical_year,
                beatport_id,
                tidal_id,
                qobuz_id,
                merged_into_id,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            [
                (
                    1,
                    "id:alpha",
                    "Alpha",
                    "Tune",
                    "Alpha EP",
                    "House",
                    "Deep",
                    124.0,
                    320.0,
                    "8A",
                    2024,
                    "BP1",
                    "TD1",
                    "QZ1",
                    None,
                ),
                (
                    2,
                    "id:orphan",
                    "Orphan",
                    "Lost",
                    "Lost EP",
                    "Techno",
                    "Peak",
                    122.0,
                    300.0,
                    "9A",
                    2020,
                    "",
                    "",
                    "",
                    None,
                ),
                (
                    3,
                    "id:missing_bpm",
                    "Gamma",
                    "Runner",
                    "Silent EP",
                    "Ambient",
                    "Drone",
                    None,
                    280.0,
                    "10A",
                    2019,
                    "",
                    "",
                    "",
                    None,
                ),
                (
                    4,
                    "id:delta",
                    "Delta",
                    "Anthem",
                    "Delta EP",
                    "Techno",
                    "Peak",
                    126.0,
                    310.0,
                    "9A",
                    2021,
                    "",
                    "",
                    "",
                    None,
                ),
                (
                    5,
                    "id:alpha-merged",
                    "Alpha",
                    "Tune",
                    "Alpha EP",
                    "House",
                    "Deep",
                    124.0,
                    321.0,
                    "8A",
                    2024,
                    "BP1",
                    "",
                    "",
                    1,
                ),
                (
                    6,
                    "id:echo",
                    "Echo",
                    "Fallback",
                    "Echo EP",
                    "Breaks",
                    "Tool",
                    110.0,
                    305.0,
                    "6A",
                    2018,
                    "",
                    "",
                    "",
                    None,
                ),
                (
                    7,
                    "id:no-asset",
                    "Hollow",
                    "Ghost",
                    "Missing EP",
                    "Minimal",
                    "Dub",
                    118.0,
                    290.0,
                    "11A",
                    2017,
                    "",
                    "",
                    "",
                    None,
                ),
            ],
        )
        conn.executemany(
            (
                "INSERT INTO asset_file "
                "(id, path, duration_s, sample_rate, bit_depth, bitrate, integrity_state) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            [
                (11, "/root/alpha_preferred.m4a", 320.0, 44100, 16, 256000, "ok"),
                (12, "/root/alpha_merged.flac", 321.0, 48000, 24, None, "ok"),
                (21, "/root/orphan.flac", 300.0, 44100, 16, None, "ok"),
                (31, "/root/gamma.flac", 280.0, 44100, 16, None, "ok"),
                (32, "/root/gamma.mp3", 280.0, 44100, 16, 320000, "ok"),
                (41, "/root/delta-low.mp3", 310.0, 44100, 16, 192000, "ok"),
                (42, "/root/delta-high.mp3", 310.0, 44100, 16, 320000, "ok"),
                (61, "/root/echo.m4a", 305.0, 48000, 24, 256000, "ok"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (11, 1),
                (12, 5),
                (21, 2),
                (31, 3),
                (32, 3),
                (41, 4),
                (42, 4),
                (61, 6),
            ],
        )
        conn.executemany(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            [
                (1, 11, 1.0, "{}", 1),
                (2, 21, 1.0, "{}", 1),
                (5, 12, 1.0, "{}", 1),
            ],
        )
        conn.executemany(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, ?, '{}', 1)",
            [
                (1, "active"),
                (2, "orphan"),
                (3, "active"),
                (4, "active"),
                (6, "active"),
                (7, "active"),
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
    assert [row["identity_id"] for row in rows_active] == ["1", "4", "6", "3"]

    out_orphan = tmp_path / "orphan.csv"
    proc_orphan = _run_export(db=db, out=out_orphan, extra_args=["--scope", "active+orphan"])
    assert proc_orphan.returncode == 0, f"STDOUT:\n{proc_orphan.stdout}\nSTDERR:\n{proc_orphan.stderr}"
    assert "view: v_dj_pool_candidates_active_orphan_v3" in proc_orphan.stdout
    rows_orphan = _read_csv(out_orphan)
    assert [row["identity_id"] for row in rows_orphan] == ["1", "4", "6", "3", "2"]

    out_all = tmp_path / "all.csv"
    proc_all = _run_export(db=db, out=out_all, extra_args=["--scope", "all"])
    assert proc_all.returncode == 0, f"STDOUT:\n{proc_all.stdout}\nSTDERR:\n{proc_all.stderr}"
    assert "view: v_dj_pool_candidates_v3" in proc_all.stdout
    rows_all = _read_csv(out_all)
    assert [row["identity_id"] for row in rows_all] == ["1", "4", "6", "3", "2"]
    assert "excluded_no_preferred: 1" in proc_all.stdout


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


def test_export_groups_merged_identities_and_respects_preferred_asset(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    out = tmp_path / "identity.csv"

    proc = _run_export(db=db, out=out, extra_args=["--scope", "active"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    fieldnames, rows = _read_csv_with_header(out)
    assert "canonical_artist" in fieldnames
    assert "canonical_title" in fieldnames
    assert "canonical_album" in fieldnames
    assert "canonical_bpm" in fieldnames
    assert "canonical_key" in fieldnames
    assert "canonical_genre" in fieldnames
    assert "canonical_sub_genre" in fieldnames
    assert "canonical_year" in fieldnames
    assert "selected_asset_path" in fieldnames
    assert "selected_asset_format" in fieldnames
    assert "selected_asset_bitrate" in fieldnames
    assert "tidal_id" in fieldnames
    assert "qobuz_id" in fieldnames

    assert [row["identity_id"] for row in rows].count("1") == 1
    assert "5" not in [row["identity_id"] for row in rows]

    row_alpha = next(row for row in rows if row["identity_id"] == "1")
    assert row_alpha["canonical_artist"] == "Alpha"
    assert row_alpha["canonical_title"] == "Tune"
    assert row_alpha["canonical_album"] == "Alpha EP"
    assert row_alpha["canonical_bpm"] == "124.0"
    assert row_alpha["canonical_key"] == "8A"
    assert row_alpha["canonical_genre"] == "House"
    assert row_alpha["canonical_sub_genre"] == "Deep"
    assert row_alpha["canonical_year"] == "2024"
    assert row_alpha["beatport_id"] == "BP1"
    assert row_alpha["tidal_id"] == "TD1"
    assert row_alpha["qobuz_id"] == "QZ1"
    assert row_alpha["selected_asset_path"] == "/root/alpha_preferred.m4a"
    assert row_alpha["selected_asset_format"] == "m4a"
    assert row_alpha["selected_asset_bitrate"] == "256000"


def test_merged_identity_asset_does_not_override_canonical_preferred(tmp_path: Path) -> None:
    """Identity 5 is merged into identity 1.

    Identity 5 has its own preferred_asset row pointing to asset 12 (alpha_merged.flac).
    Identity 1 has its own preferred_asset row pointing to asset 11 (alpha_preferred.m4a).

    The export must:
    - Emit exactly one row for identity 1 (the canonical root).
    - Select asset 11 for identity 1, NOT asset 12 from the merged identity.
    - Omit identity 5 entirely from the output.
    """
    db = _create_fixture_db(tmp_path)
    out = tmp_path / "merge_isolation.csv"

    proc = _run_export(db=db, out=out, extra_args=["--scope", "active"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    rows = _read_csv(out)
    ids = [row["identity_id"] for row in rows]

    # merged identity must not appear
    assert "5" not in ids

    # canonical identity appears exactly once
    assert ids.count("1") == 1

    row_1 = next(row for row in rows if row["identity_id"] == "1")
    # must use canonical's own preferred asset, not the merged identity's asset
    assert row_1["selected_asset_path"] == "/root/alpha_preferred.m4a"
    assert row_1["selected_asset_id"] == "11"
    # must not select the merged identity's flac (asset 12)
    assert row_1["selected_asset_path"] != "/root/alpha_merged.flac"


def test_fallback_asset_selection_prefers_flac_then_highest_mp3_then_remaining(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    out = tmp_path / "fallbacks.csv"

    proc = _run_export(db=db, out=out, extra_args=["--scope", "active"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    rows = _read_csv(out)

    row_gamma = next(row for row in rows if row["identity_id"] == "3")
    assert row_gamma["selected_asset_path"] == "/root/gamma.flac"
    assert row_gamma["selected_asset_format"] == "flac"
    assert row_gamma["selected_asset_bitrate"] == ""

    row_delta = next(row for row in rows if row["identity_id"] == "4")
    assert row_delta["selected_asset_path"] == "/root/delta-high.mp3"
    assert row_delta["selected_asset_format"] == "mp3"
    assert row_delta["selected_asset_bitrate"] == "320000"

    row_echo = next(row for row in rows if row["identity_id"] == "6")
    assert row_echo["selected_asset_path"] == "/root/echo.m4a"
    assert row_echo["selected_asset_format"] == "m4a"
    assert row_echo["selected_asset_bitrate"] == "256000"


def test_export_connection_is_query_only(tmp_path: Path) -> None:
    db = _create_fixture_db(tmp_path)
    module = _load_export_module()

    conn = module._connect_ro(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO track_identity (identity_key, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES ('identity:new', '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')"
            )
    finally:
        conn.close()


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
