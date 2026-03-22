from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAN_SCRIPT = PROJECT_ROOT / "tools" / "review" / "plan_fpcalc_promote_unique_to_final_library.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("plan_fpcalc_promote_unique_to_final_library", PLAN_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_planner_uses_streaminfo_md5_as_exact_audio_identity(tmp_path, monkeypatch) -> None:
    module = _load_module()

    db_path = tmp_path / "music.db"
    source_root = tmp_path / "source"
    final_root = tmp_path / "final"
    dest_root = tmp_path / "dest"
    out_dir = tmp_path / "artifacts"
    quarantine_root = tmp_path / "quarantine"

    source_root.mkdir()
    final_root.mkdir()
    dest_root.mkdir()
    out_dir.mkdir()
    quarantine_root.mkdir()

    source_path = source_root / "source-track.flac"
    final_path = final_root / "final-track.flac"
    source_path.write_bytes(b"source")
    final_path.write_bytes(b"final")

    metadata_json = json.dumps(
        {
            "artist": "Example Artist",
            "title": "Example Title",
            "album": "Example Album",
            "date": "2024",
            "tracknumber": "01",
        }
    )

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT,
                size INTEGER,
                duration REAL,
                sample_rate INTEGER,
                bit_depth INTEGER,
                bitrate INTEGER,
                fingerprint TEXT,
                streaminfo_md5 TEXT,
                flac_ok INTEGER,
                integrity_state TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO files (
                path, size, duration, sample_rate, bit_depth, bitrate,
                fingerprint, streaminfo_md5, flac_ok, integrity_state, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(final_path),
                    100,
                    250.0,
                    44100,
                    16,
                    900000,
                    None,
                    "same-streaminfo-md5",
                    1,
                    "valid",
                    metadata_json,
                ),
                (
                    str(source_path),
                    100,
                    250.0,
                    44100,
                    16,
                    900000,
                    None,
                    "same-streaminfo-md5",
                    1,
                    "valid",
                    metadata_json,
                ),
            ],
        )
        conn.commit()

    monkeypatch.setattr(module, "_volume_name", lambda _path: "TESTVOL")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(PLAN_SCRIPT),
            "--db",
            str(db_path),
            "--source-root",
            str(source_root),
            "--final-root",
            str(final_root),
            "--dest-root",
            str(dest_root),
            "--stash-folder-name",
            "stash",
            "--quarantine-root",
            str(quarantine_root),
            "--quarantine-missing-fp",
                "--out-dir",
                str(out_dir),
                "--stamp",
                "20260312_180000",
            ],
        )

    rc = module.main()

    assert rc == 0

    summary = json.loads((out_dir / "plan_fpcalc_unique_final_summary_20260312_180000.json").read_text(encoding="utf-8"))
    stash_rows = _read_csv(out_dir / "plan_stash_fpcalc_unique_final_20260312_180000.csv")
    quarantine_rows = _read_csv(out_dir / "plan_quarantine_fpcalc_unique_final_20260312_180000.csv")
    promote_rows = _read_csv(out_dir / "plan_promote_fpcalc_unique_final_20260312_180000.csv")

    assert summary["scoped_files_with_fp"] == 0
    assert summary["scoped_files_missing_fp"] == 1
    assert summary["scoped_files_with_audio_id"] == 1
    assert summary["scoped_files_missing_audio_id"] == 0
    assert summary["final_audio_ids_distinct"] == 1
    assert summary["planned"]["stash_move"] == 1
    assert summary["planned"]["quarantine_move"] == 0
    assert promote_rows == []
    assert len(stash_rows) == 1
    assert stash_rows[0]["path"] == str(source_path)
    assert stash_rows[0]["reason"] == "stash_fpcalc_in_final"
    assert quarantine_rows == []
