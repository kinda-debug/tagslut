"""Compatibility tests for archived scripts/archive/build_export_v3.py."""

from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.dj_profile import ensure_schema
from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_db_and_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    src_root = tmp_path / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    src_a = src_root / "alpha.flac"
    src_b = src_root / "beta.flac"
    src_a.write_bytes(b"alpha-bytes")
    src_b.write_bytes(b"beta-bytes")

    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        ensure_schema(conn)
        conn.executemany(
            (
                "INSERT INTO track_identity "
                "(id, identity_key, canonical_artist, canonical_title, canonical_genre, merged_into_id, "
                "ingested_at, ingestion_method, ingestion_source, ingestion_confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            [
                (1, "id:a", "Alpha", "Tune", "House", None, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (2, "id:b", "Beta", "Peak", "Techno", None, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_file (id, path, content_sha256, mtime) VALUES (?, ?, ?, ?)",
            [
                (11, str(src_a), "a4f9e7a9bb7d6c4f4a6ea0f3f3151803f2d3f7035508ed9d95b3f80e7cecc665", 1.0),
                (21, str(src_b), "2e3b1fd1f2f8a5df1e4e7fe0e6bb70f4f44d8f093bcf5d67272ed8f76b56d5b5", 2.0),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [(11, 1), (21, 2)],
        )
        conn.executemany(
            (
                "INSERT INTO preferred_asset "
                "(identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)"
            ),
            [(1, 11, 1.0, "{}", 1), (2, 21, 1.0, "{}", 1)],
        )
        conn.executemany(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (?, 'active', '{}', 1)",
            [(1,), (2,)],
        )
        conn.execute(
            (
                "INSERT INTO dj_track_profile "
                "(identity_id, set_role, rating, energy, dj_tags_json) "
                "VALUES (1, 'builder', 4, 7, '[\"groovy\"]')"
            )
        )
        conn.commit()
    finally:
        conn.close()
    return db, src_a, src_b


def _run_builder(
    *,
    db: Path,
    out_dir: Path,
    manifest: Path | None = None,
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/archive/build_export_v3.py",
        "--db",
        str(db),
        "--out-dir",
        str(out_dir),
    ]
    if manifest is not None:
        cmd.extend(["--manifest", str(manifest)])
    if extra:
        cmd.extend(extra)
    return subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)


def _read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_plan_mode_writes_manifest_and_no_files_created(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    manifest = tmp_path / "plan_manifest.csv"

    proc = _run_builder(db=db, out_dir=out_dir, manifest=manifest)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert manifest.exists()
    rows = _read_manifest(manifest)
    assert len(rows) == 2
    assert rows[0]["dest_path"] <= rows[1]["dest_path"]
    exported_files = [p for p in out_dir.rglob("*") if p.is_file()]
    assert exported_files == []


def test_execute_copy_creates_files_and_receipts(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"

    proc = _run_builder(db=db, out_dir=out_dir, extra=["--execute", "--layout", "flat"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    copied = [
        p
        for p in out_dir.rglob("*")
        if p.is_file() and p.name not in {"manifest.csv", "receipts.jsonl"}
    ]
    assert len(copied) == 2
    receipts = out_dir / "receipts.jsonl"
    assert receipts.exists()
    lines = [line for line in receipts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert "identity_id" in payload
    assert payload["action"] in {"copy", "transcode"}


def test_overwrite_never_skips_existing_file(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = out_dir / "builder" / "Alpha - Tune [1].flac"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"old")

    proc = _run_builder(
        db=db,
        out_dir=out_dir,
        extra=["--execute", "--overwrite", "never", "--layout", "by_role"],
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    manifest = out_dir / "manifest.csv"
    rows = _read_manifest(manifest)
    target = next(row for row in rows if row["identity_id"] == "1")
    assert target["action"] == "skip"
    assert target["reason"] == "exists_overwrite_never"
    assert existing.read_bytes() == b"old"
