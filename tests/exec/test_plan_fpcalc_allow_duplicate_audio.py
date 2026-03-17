from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _create_files_table(conn: sqlite3.Connection) -> None:
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


def _insert_file(
    conn: sqlite3.Connection,
    *,
    path: Path,
    fingerprint: str,
    metadata: dict[str, str],
) -> None:
    conn.execute(
        """
        INSERT INTO files (
            path, size, duration, sample_rate, bit_depth, bitrate,
            fingerprint, streaminfo_md5, flac_ok, integrity_state, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(path),
            123,
            180.0,
            44100,
            16,
            0,
            fingerprint,
            None,
            1,
            "valid",
            json.dumps(metadata),
        ),
    )


def _latest(out_dir: Path, pattern: str) -> Path:
    matches = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    assert matches, f"missing {pattern} in {out_dir}"
    return matches[0]


def test_plan_fpcalc_allow_duplicate_audio_promotes_when_layout_differs(tmp_path: Path) -> None:
    final_root = tmp_path / "FINAL"
    source_root = tmp_path / "BATCH"
    out_dir = tmp_path / "out"
    final_root.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Same audio fingerprint, but different album layouts:
    # - Existing final library track: single/EP
    # - Incoming batch track: compilation
    fp = "fpcalc:test123"

    final_file = final_root / "Artist" / "(2026) Single" / "Artist – (2026) Single – 01 Track.flac"
    final_file.parent.mkdir(parents=True, exist_ok=True)
    final_file.write_text("x", encoding="utf-8")

    source_file = source_root / "Various Artists" / "(2026) Compilation" / "Some Artist – (2026) Compilation – 01 Track.flac"
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text("x", encoding="utf-8")

    db_path = tmp_path / "music.db"
    conn = sqlite3.connect(str(db_path))
    try:
        _create_files_table(conn)
        _insert_file(
            conn,
            path=final_file,
            fingerprint=fp,
            metadata={
                "albumartist": "Artist",
                "artist": "Artist",
                "album": "Single",
                "title": "Track",
                "date": "2026-01-01",
                "tracknumber": "1",
            },
        )
        _insert_file(
            conn,
            path=source_file,
            fingerprint=fp,
            metadata={
                "albumartist": "Various Artists",
                "artist": "Some Artist",
                "album": "Compilation",
                "title": "Track",
                "date": "2026-01-01",
                "tracknumber": "1",
            },
        )
        conn.commit()
    finally:
        conn.close()

    base_cmd = [
        sys.executable,
        "tools/review/plan_fpcalc_promote_unique_to_final_library.py",
        "--db",
        str(db_path),
        "--source-root",
        str(source_root),
        "--final-root",
        str(final_root),
        "--dest-root",
        str(final_root),
        "--prefer-root",
        str(source_root),
        "--stash-folder-name",
        "../FIX",
        "--out-dir",
        str(out_dir),
        "--stamp",
        "20260101_000000",
    ]

    # Default behavior: stash duplicates already in FINAL.
    r1 = subprocess.run(base_cmd, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    summary1 = json.loads(_latest(out_dir, "plan_fpcalc_unique_final_summary_*.json").read_text(encoding="utf-8"))
    planned1 = summary1["planned"]
    assert planned1["promote_move"] == 0
    # In non-/Volumes test paths, stash rows may be omitted; the important contract
    # is that duplicates in FINAL are not promoted unless explicitly allowed.
    assert planned1["stash_move"] == 0

    # Allow-duplicate behavior: promote when layout differs and dest doesn't exist.
    r2 = subprocess.run(base_cmd + ["--allow-duplicate-audio"], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    summary2 = json.loads(_latest(out_dir, "plan_fpcalc_unique_final_summary_*.json").read_text(encoding="utf-8"))
    planned2 = summary2["planned"]
    assert planned2["promote_move"] == 1
    assert planned2["stash_move"] == 0
