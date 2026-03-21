"""Tests for scripts/dj/build_pool_v3.py."""

from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.dj_profile import ensure_schema
from tagslut.storage.v3.schema import create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_POOL_SCRIPT = PROJECT_ROOT / "scripts" / "dj" / "build_pool_v3.py"


def _load_build_pool_module():
    spec = importlib.util.spec_from_file_location("build_pool_v3", BUILD_POOL_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_db_and_sources(tmp_path: Path, *, second_source_is_dir: bool = False) -> tuple[Path, Path, Path]:
    src_root = tmp_path / "src"
    src_root.mkdir(parents=True, exist_ok=True)
    src_a = src_root / "alpha.flac"
    src_b = src_root / "beta.flac"
    src_a.write_bytes(b"alpha-bytes")
    if second_source_is_dir:
        src_b.mkdir()
    else:
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
        "scripts/dj/build_pool_v3.py",
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


def test_select_rows_emits_canonical_aliases(tmp_path: Path) -> None:
    module = _load_build_pool_module()
    db, src_a, _src_b = _create_db_and_sources(tmp_path)

    conn = module._connect_db(db)
    try:
        rows = module._select_rows(
            conn,
            scope="active",
            min_rating=None,
            min_energy=None,
            set_roles=[],
            only_profiled=False,
            limit=None,
            identity_ids=None,
        )
    finally:
        conn.close()

    assert len(rows) == 2
    row = rows[0]
    assert row["canonical_artist"] in {"Alpha", "Beta"}
    assert row["canonical_title"] in {"Tune", "Peak"}
    assert row["selected_asset_id"] in {11, 21}
    assert row["selected_asset_path"] in {str(src_a), str(_src_b)}


def test_row_source_path_prefers_selected_asset_path_then_legacy_aliases(tmp_path: Path) -> None:
    module = _load_build_pool_module()

    assert module._row_source_path(
        {
            "selected_asset_path": "/music/new.flac",
            "preferred_path": "/music/old.flac",
            "source_path": "/music/older.flac",
        }
    ) == "/music/new.flac"
    assert module._row_source_path(
        {
            "preferred_path": "/music/old.flac",
            "source_path": "/music/older.flac",
        }
    ) == "/music/old.flac"
    assert module._row_source_path({"source_path": "/music/older.flac"}) == "/music/older.flac"


def test_dest_path_accepts_canonical_export_shape(tmp_path: Path) -> None:
    module = _load_build_pool_module()

    dest = module._dest_path(
        tmp_path,
        {
            "identity_id": 7,
            "canonical_artist": "Canonical Artist",
            "canonical_title": "Canonical Title",
            "canonical_genre": "Afro House",
            "selected_asset_path": "/music/source.flac",
            "set_role": "builder",
        },
        "by_genre",
        "copy",
    )

    assert dest == tmp_path / "Afro House" / "Canonical Artist - Canonical Title [7].flac"


def test_plan_writes_manifest_and_no_files_created(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    manifest = tmp_path / "plan_manifest.csv"

    proc = _run_builder(db=db, out_dir=out_dir, manifest=manifest)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert manifest.exists()
    rows = _read_manifest(manifest)
    assert len(rows) == 2
    exported_files = [p for p in out_dir.rglob("*") if p.is_file()]
    assert exported_files == []


def test_plan_accepts_legacy_args_and_writes_mtime_field(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    manifest = tmp_path / "plan_manifest.csv"

    proc = _run_builder(
        db=db,
        out_dir=out_dir,
        manifest=manifest,
        extra=[
            "--source-mode",
            "preferred",
            "--format",
            "mp3",
            "--ffmpeg-path",
            "/tmp/not-used-in-plan-mode",
        ],
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_manifest(manifest)
    assert len(rows) == 2
    assert rows[0]["mtime"] in {"1.0", "2.0"}
    assert rows[1]["mtime"] in {"1.0", "2.0"}
    assert rows[0]["dest_path"].endswith(".mp3")
    assert rows[1]["dest_path"].endswith(".mp3")


def test_plan_filters_to_identity_id_file(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    manifest = tmp_path / "plan_manifest.csv"
    identity_ids = tmp_path / "identity_ids.txt"
    identity_ids.write_text("2\n", encoding="utf-8")

    proc = _run_builder(
        db=db,
        out_dir=out_dir,
        manifest=manifest,
        extra=["--identity-id-file", str(identity_ids)],
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_manifest(manifest)
    assert len(rows) == 1
    assert rows[0]["identity_id"] == "2"


def test_execute_copy_creates_files_and_receipts(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"

    proc = _run_builder(db=db, out_dir=out_dir, extra=["--execute", "--layout", "flat"])
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    copied = [p for p in out_dir.rglob("*") if p.is_file() and p.name not in {"manifest.csv", "receipts.jsonl"}]
    assert len(copied) == 2
    receipts = out_dir / "receipts.jsonl"
    assert receipts.exists()
    lines = [line for line in receipts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["tool"] == "build_pool_v3"
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
    rows = _read_manifest(out_dir / "manifest.csv")
    target = next(row for row in rows if row["identity_id"] == "1")
    assert target["action"] == "skip"
    assert target["reason"] == "exists_overwrite_never"
    assert existing.read_bytes() == b"old"


def test_fail_fast_writes_failure_log_before_exiting(tmp_path: Path) -> None:
    db, _src_a, src_b = _create_db_and_sources(tmp_path, second_source_is_dir=True)
    out_dir = tmp_path / "export"

    proc = _run_builder(
        db=db,
        out_dir=out_dir,
        extra=["--execute", "--layout", "flat", "--fail-fast"],
    )

    assert proc.returncode == 1, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert str(src_b) in proc.stderr

    failure_path = out_dir / "export_failures.jsonl"
    assert failure_path.exists()
    payloads = [
        json.loads(line)
        for line in failure_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(payloads) == 1
    assert payloads[0]["source_path"] == str(src_b)

    receipts = out_dir / "receipts.jsonl"
    assert receipts.exists()
    lines = [line for line in receipts.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1


def test_plan_skips_rows_missing_artist_or_title_for_mp3_exports(tmp_path: Path) -> None:
    db, _src_a, _src_b = _create_db_and_sources(tmp_path)
    out_dir = tmp_path / "export"
    manifest = tmp_path / "plan_manifest.csv"

    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "UPDATE track_identity SET canonical_artist = NULL, canonical_title = NULL WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_builder(
        db=db,
        out_dir=out_dir,
        manifest=manifest,
        extra=["--format", "mp3", "--ffmpeg-path", "/tmp/not-used-in-plan-mode"],
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    rows = _read_manifest(manifest)
    skipped = next(row for row in rows if row["identity_id"] == "1")
    assert skipped["action"] == "skip"
    assert skipped["reason"] == "missing_artist_or_title"
    assert skipped["dest_path"] == ""
