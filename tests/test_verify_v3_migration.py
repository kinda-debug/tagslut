"""Tests for scripts/db/verify_v3_migration.py."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_v2_db(
    path: Path,
    *,
    total_assets: int,
    integrity_done: int,
    sha256_done: int,
    enriched_done: int,
) -> Path:
    db = path / "v2.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                integrity_checked_at TEXT,
                sha256_checked_at TEXT,
                enriched_at TEXT
            )
            """
        )
        rows = []
        for idx in range(total_assets):
            rows.append(
                (
                    f"/music/{idx + 1}.flac",
                    "2026-03-01T00:00:00Z" if idx < integrity_done else None,
                    "2026-03-01T00:00:00Z" if idx < sha256_done else None,
                    "2026-03-01T00:00:00Z" if idx < enriched_done else None,
                )
            )
        conn.executemany(
            "INSERT INTO files (path, integrity_checked_at, sha256_checked_at, enriched_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _create_v3_db(
    path: Path,
    *,
    assets_total: int,
    links_total: int,
    integrity_done: int,
    sha256_done: int,
    enriched_done: int,
) -> Path:
    db = path / "v3.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE asset_file (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                integrity_checked_at TEXT,
                sha256_checked_at TEXT
            );
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identity_key TEXT NOT NULL UNIQUE,
                enriched_at TEXT
            );
            CREATE TABLE asset_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                identity_id INTEGER NOT NULL
            );
            """
        )
        asset_rows = []
        identity_rows = []
        for idx in range(assets_total):
            asset_rows.append(
                (
                    idx + 1,
                    f"/music/{idx + 1}.flac",
                    "2026-03-01T00:00:00Z" if idx < integrity_done else None,
                    "2026-03-01T00:00:00Z" if idx < sha256_done else None,
                )
            )
            identity_rows.append(
                (
                    idx + 1,
                    f"id:{idx + 1}",
                    "2026-03-01T00:00:00Z" if idx < enriched_done else None,
                )
            )

        conn.executemany(
            "INSERT INTO asset_file (id, path, integrity_checked_at, sha256_checked_at) VALUES (?, ?, ?, ?)",
            asset_rows,
        )
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, enriched_at) VALUES (?, ?, ?)",
            identity_rows,
        )

        link_rows = []
        for idx in range(links_total):
            link_rows.append((idx + 1, idx + 1))
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id) VALUES (?, ?)",
            link_rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _run_verify(*, v2: Path, v3: Path, strict: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/db/verify_v3_migration.py",
        "--v2",
        str(v2),
        "--v3",
        str(v3),
    ]
    if strict:
        cmd.append("--strict")
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_verify_v3_migration_passes_strict(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=3,
        integrity_done=2,
        sha256_done=1,
        enriched_done=1,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=3,
        links_total=3,
        integrity_done=2,
        sha256_done=1,
        enriched_done=1,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=True)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "OK: v3 migration verification passed" in proc.stdout
    assert "v2.assets_total:    3" in proc.stdout
    assert "v3.assets_total:    3" in proc.stdout


def test_verify_v3_migration_fails_when_v3_missing(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=1,
        integrity_done=1,
        sha256_done=1,
        enriched_done=0,
    )
    missing_v3 = tmp_path / "missing_v3.db"

    proc = _run_verify(v2=v2, v3=missing_v3, strict=False)
    assert proc.returncode != 0
    assert "v3 db not found; run migrate-v2-to-v3" in proc.stdout


def test_verify_v3_migration_fails_when_asset_link_invariant_breaks(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=3,
        integrity_done=2,
        sha256_done=2,
        enriched_done=1,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=3,
        links_total=2,
        integrity_done=2,
        sha256_done=2,
        enriched_done=1,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=False)
    assert proc.returncode != 0
    assert "invariant failed: COUNT(asset_file) must equal COUNT(asset_link)" in proc.stdout
    assert "examples.link_missing_assets" in proc.stdout
    assert "path=/music/3.flac" in proc.stdout


def test_verify_v3_migration_strict_fails_on_integrity_regression(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=2,
        integrity_done=2,
        sha256_done=1,
        enriched_done=0,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=2,
        links_total=2,
        integrity_done=1,
        sha256_done=1,
        enriched_done=0,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=True)
    assert proc.returncode != 0
    assert "strict: integrity_done regressed" in proc.stdout


def test_verify_v3_migration_fails_when_integrity_rows_lost(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=2,
        integrity_done=2,
        sha256_done=2,
        enriched_done=0,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=2,
        links_total=2,
        integrity_done=1,
        sha256_done=2,
        enriched_done=0,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=False)
    assert proc.returncode != 0
    assert "integrity preservation failed" in proc.stdout
    assert "examples.integrity_rows_lost" in proc.stdout
    assert "path=/music/2.flac" in proc.stdout


def test_verify_v3_migration_fails_when_sha256_rows_lost(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=2,
        integrity_done=2,
        sha256_done=2,
        enriched_done=0,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=2,
        links_total=2,
        integrity_done=2,
        sha256_done=1,
        enriched_done=0,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=False)
    assert proc.returncode != 0
    assert "sha256 preservation failed" in proc.stdout
    assert "examples.sha256_rows_lost" in proc.stdout
    assert "path=/music/2.flac" in proc.stdout


def test_verify_v3_migration_fails_when_enriched_rows_lose_identity_enriched_at(tmp_path: Path) -> None:
    v2 = _create_v2_db(
        tmp_path,
        total_assets=2,
        integrity_done=2,
        sha256_done=2,
        enriched_done=1,
    )
    v3 = _create_v3_db(
        tmp_path,
        assets_total=2,
        links_total=2,
        integrity_done=2,
        sha256_done=2,
        enriched_done=0,
    )

    proc = _run_verify(v2=v2, v3=v3, strict=False)
    assert proc.returncode != 0
    assert "enriched_at preservation failed" in proc.stdout
    assert "examples.enriched_rows_lost" in proc.stdout
    assert "path=/music/1.flac" in proc.stdout
