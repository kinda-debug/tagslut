from __future__ import annotations

import csv
import importlib.util as _ilu
from pathlib import Path
import sqlite3


_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "db" / "migration_report_v2_to_v3.py"
_SPEC = _ilu.spec_from_file_location("migration_report_v2_to_v3", _SCRIPT)
_MOD = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)

build_report = _MOD.build_report


def _create_v2_db(path: Path) -> Path:
    db = path / "v2.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                integrity_checked_at TEXT,
                sha256_checked_at TEXT,
                enriched_at TEXT,
                canonical_isrc TEXT,
                isrc TEXT,
                beatport_id TEXT,
                canonical_artist TEXT,
                canonical_title TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO files (
                path, integrity_checked_at, sha256_checked_at, enriched_at,
                canonical_isrc, isrc, beatport_id, canonical_artist, canonical_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "/music/a.flac",
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T00:00:00Z",
                    "2026-02-03T00:00:00Z",
                    "USAAA1111111",
                    "USAAA1111111",
                    None,
                    "Artist A",
                    "Track A",
                ),
                (
                    "/music/b.flac",
                    "2026-02-02T00:00:00Z",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "Artist B",
                    "Track B",
                ),
                (
                    "/music/c.flac",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _create_v3_db(path: Path) -> Path:
    db = path / "v3.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            CREATE TABLE asset_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE,
                integrity_checked_at TEXT,
                sha256_checked_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT UNIQUE,
                isrc TEXT,
                enriched_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE asset_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER,
                identity_id INTEGER,
                active INTEGER DEFAULT 1
            )
            """
        )

        conn.executemany(
            "INSERT INTO asset_file (id, path, integrity_checked_at, sha256_checked_at) VALUES (?, ?, ?, ?)",
            [
                (1, "/music/a.flac", "2026-02-01T00:00:00Z", "2026-02-01T00:00:00Z"),
                (2, "/music/b.flac", "2026-02-02T00:00:00Z", None),
                (3, "/music/c.flac", None, None),
            ],
        )
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, isrc, enriched_at) VALUES (?, ?, ?, ?)",
            [
                (11, "isrc:USAAA1111111", "USAAA1111111", "2026-02-03T00:00:00Z"),
                (12, "unidentified:chk_b", None, None),
                (13, "beatport:BP-9", None, None),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (1, 11),
                (2, 12),
                (3, 13),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_build_report_writes_expected_summary_and_deterministic_sample(tmp_path: Path) -> None:
    v2 = _create_v2_db(tmp_path)
    v3 = _create_v3_db(tmp_path)
    summary = tmp_path / "summary.csv"
    sample = tmp_path / "sample.csv"

    matched, sampled = build_report(
        v2_path=v2,
        v3_path=v3,
        summary_out=summary,
        sample_out=sample,
        sample_size=2,
        seed=1234,
    )
    assert matched == 3
    assert sampled == 2

    summary_rows = {row["metric"]: row for row in _read_csv_rows(summary)}
    assert summary_rows["assets_count"]["v2_count"] == "3"
    assert summary_rows["assets_count"]["v3_count"] == "3"
    assert summary_rows["with_integrity_checked_at"]["v2_count"] == "2"
    assert summary_rows["with_integrity_checked_at"]["v3_count"] == "2"
    assert summary_rows["with_sha256_checked_at"]["v2_count"] == "1"
    assert summary_rows["with_sha256_checked_at"]["v3_count"] == "1"
    assert summary_rows["with_enriched_at"]["v2_count"] == "1"
    assert summary_rows["with_enriched_at"]["v3_count"] == "1"
    assert summary_rows["with_canonical_isrc"]["v2_count"] == "1"
    assert summary_rows["with_canonical_isrc"]["v3_count"] == "1"
    assert summary_rows["unidentified_identities_count"]["v2_count"] == "1"
    assert summary_rows["unidentified_identities_count"]["v3_count"] == "1"

    first_sample_rows = _read_csv_rows(sample)
    assert len(first_sample_rows) == 2

    # Deterministic sample selection with fixed seed.
    sample_2 = tmp_path / "sample_2.csv"
    _, sampled_2 = build_report(
        v2_path=v2,
        v3_path=v3,
        summary_out=tmp_path / "summary_2.csv",
        sample_out=sample_2,
        sample_size=2,
        seed=1234,
    )
    assert sampled_2 == 2
    second_sample_rows = _read_csv_rows(sample_2)
    assert first_sample_rows == second_sample_rows

