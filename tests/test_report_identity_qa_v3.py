"""Tests for scripts/db/report_identity_qa_v3.py."""

from __future__ import annotations

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_v3_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)

        conn.executemany(
            """
            INSERT INTO asset_file (
                id, path, duration_measured_ms, sample_rate, bit_depth
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, "/music/a1.flac", 100000, 44100, 16),
                (2, "/music/a2.flac", 103500, 48000, 24),
                (3, "/music/b1.flac", 100200, 44100, 16),
                (4, "/music/c1.flac", 101000, 44100, 16),
                (5, "/music/d1.flac", 101100, 44100, 16),
            ],
        )

        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                isrc,
                beatport_id,
                tidal_id,
                qobuz_id,
                spotify_id,
                canonical_artist,
                canonical_title,
                enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    "isrc:ISRC-1",
                    "ISRC-1",
                    "BP-1",
                    "",
                    "",
                    "",
                    "Artist 1",
                    "Track 1",
                    "2026-03-01T00:00:00Z",
                ),
                (
                    2,
                    "unidentified:abc",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "Artist 2",
                    "",
                    "",
                ),
                (
                    3,
                    "isrc:DUPISRC:1",
                    "DUPISRC",
                    "BP-DUP",
                    "",
                    "",
                    "",
                    "Artist 3",
                    "Track 3",
                    "2026-03-01T00:00:00Z",
                ),
                (
                    4,
                    "isrc:DUPISRC:2",
                    "DUPISRC",
                    "BP-DUP",
                    "",
                    "",
                    "",
                    "Artist 4",
                    "Track 4",
                    "",
                ),
            ],
        )

        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (1, 1),
                (2, 1),
                (3, 2),
                (4, 3),
                (5, 4),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _run_report(
    *,
    db_path: Path,
    out_path: Path | None = None,
    limit: int = 200,
    include_orphans: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/db/report_identity_qa_v3.py",
        "--db",
        str(db_path),
        "--limit",
        str(limit),
    ]
    if include_orphans:
        cmd.append("--include-orphans")
    if out_path is not None:
        cmd.extend(["--out", str(out_path)])
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_report_identity_qa_v3_writes_csv_and_summary(tmp_path: Path) -> None:
    db = _create_v3_fixture(tmp_path)
    out = tmp_path / "identity_qa.csv"

    proc = _run_report(db_path=db, out_path=out, limit=10)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert out.exists()
    assert "identities_total: 4" in proc.stdout
    assert "enriched_identities: 2" in proc.stdout
    assert "unidentified_identities: 1" in proc.stdout
    assert "identities_missing_core_fields: 1" in proc.stdout
    assert "identities_missing_strong_keys: 1" in proc.stdout
    assert "Duplicate ISRC groups: 1" in proc.stdout
    assert "Duplicate beatport_id groups: 1" in proc.stdout
    assert "identity_id=1 identity_key=isrc:ISRC-1 asset_count=2" in proc.stdout
    assert "duration_spread_ms=3500 mixed_quality=1" in proc.stdout

    rows = _read_csv_rows(out)
    assert len(rows) == 4
    by_id = {row["identity_id"]: row for row in rows}
    assert by_id["1"]["asset_count"] == "2"
    assert by_id["1"]["mixed_quality"] == "1"
    assert by_id["1"]["duration_spread_ms"] == "3500"
    assert by_id["1"]["missing_core_fields"] == "0"
    assert by_id["2"]["has_unidentified_key"] == "1"
    assert by_id["2"]["missing_core_fields"] == "1"
    assert by_id["2"]["isrc"] == ""
    assert by_id["2"]["beatport_id"] == ""


def test_report_identity_qa_v3_summary_only_mode(tmp_path: Path) -> None:
    db = _create_v3_fixture(tmp_path)

    proc = _run_report(db_path=db, out_path=None, limit=5)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "Counts:" in proc.stdout
    assert "Top identities by asset_count (limit=5):" in proc.stdout
    assert "csv_out:" not in proc.stdout


def test_report_identity_qa_v3_inconsistency_scope_defaults_to_active(tmp_path: Path) -> None:
    db = _create_v3_fixture(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            INSERT INTO identity_status (identity_id, status, reason_json, version)
            VALUES (?, ?, ?, ?)
            """,
            (1, "orphan", '{"forced":1}', 1),
        )
        conn.commit()
    finally:
        conn.close()

    default_scope = _run_report(db_path=db, limit=10)
    include_orphan_scope = _run_report(db_path=db, limit=10, include_orphans=True)

    assert default_scope.returncode == 0, f"STDOUT:\n{default_scope.stdout}\nSTDERR:\n{default_scope.stderr}"
    assert include_orphan_scope.returncode == 0, (
        f"STDOUT:\n{include_orphan_scope.stdout}\nSTDERR:\n{include_orphan_scope.stderr}"
    )
    assert "scope=active" in default_scope.stdout
    assert "duration_spread_ms=3500 mixed_quality=1" not in default_scope.stdout
    assert "scope=active+orphan" in include_orphan_scope.stdout
    assert "duration_spread_ms=3500 mixed_quality=1" in include_orphan_scope.stdout


def test_report_identity_qa_v3_fails_when_db_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    out = tmp_path / "identity_qa.csv"

    proc = _run_report(db_path=missing, out_path=out)
    assert proc.returncode == 2
    assert "v3 DB not found" in proc.stdout
