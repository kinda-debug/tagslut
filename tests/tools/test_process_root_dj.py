from __future__ import annotations

import importlib.util
import logging
import sqlite3
import sys
from pathlib import Path
from unittest.mock import ANY, patch

from tagslut.storage.schema import init_db

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_process_root_module():
    module_path = PROJECT_ROOT / "tools" / "review" / "process_root.py"
    spec = importlib.util.spec_from_file_location("process_root_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _init_db_file(db_path: Path, flac_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.execute("INSERT INTO files (path) VALUES (?)", (str(flac_path),))
    conn.commit()
    conn.close()


def test_run_dj_phase_dry_run_logs_enrichment_and_skips_transcode(
    tmp_path: Path,
    caplog,
) -> None:  # type: ignore[no-untyped-def]
    module = _load_process_root_module()
    root = tmp_path / "root"
    root.mkdir()
    flac_path = root / "track.flac"
    flac_path.write_bytes(b"fake")
    pool = tmp_path / "pool"
    db_path = tmp_path / "music.db"
    _init_db_file(db_path, flac_path)

    with caplog.at_level(logging.INFO), patch.object(
        module,
        "resolve_dj_tag_snapshot_for_path",
    ) as mock_snapshot, patch.object(module, "transcode_to_mp3_from_snapshot") as mock_transcode:
        mock_snapshot.return_value = type(
            "Snapshot",
            (),
            {"bpm": "128", "musical_key": "Am", "energy_1_10": None},
        )()
        module.run_dj_phase(
            db_path=db_path,
            root_path=root,
            dry_run=True,
            dj_pool_dir=pool,
        )

    row = sqlite3.connect(str(db_path)).execute(
        "SELECT dj_pool_path FROM files WHERE path = ?",
        (str(flac_path),),
    ).fetchone()

    assert "DJ snapshot: track.flac" in caplog.text
    mock_snapshot.assert_called_once_with(ANY, flac_path, run_essentia=True, dry_run=True)
    mock_transcode.assert_not_called()
    assert row is not None
    assert row[0] is None


def test_run_dj_phase_continues_transcode_when_essentia_missing(
    tmp_path: Path,
    caplog,
) -> None:  # type: ignore[no-untyped-def]
    module = _load_process_root_module()
    root = tmp_path / "root"
    root.mkdir()
    flac_path = root / "track.flac"
    flac_path.write_bytes(b"fake")
    pool = tmp_path / "pool"
    db_path = tmp_path / "music.db"
    _init_db_file(db_path, flac_path)
    mp3_path = pool / "track.mp3"

    with caplog.at_level(logging.INFO), patch.object(
        module,
        "resolve_dj_tag_snapshot_for_path",
        side_effect=[
            FileNotFoundError("missing essentia"),
            type("Snapshot", (), {"bpm": None, "musical_key": None, "energy_1_10": None})(),
        ],
    ) as mock_snapshot, patch.object(
        module, "transcode_to_mp3_from_snapshot", return_value=mp3_path
    ) as mock_transcode:
        module.run_dj_phase(
            db_path=db_path,
            root_path=root,
            dry_run=False,
            dj_pool_dir=pool,
        )

    row = sqlite3.connect(str(db_path)).execute(
        "SELECT dj_pool_path FROM files WHERE path = ?",
        (str(flac_path),),
    ).fetchone()

    assert "Essentia not found" in caplog.text
    assert mock_snapshot.call_count == 2
    mock_snapshot.assert_any_call(ANY, flac_path, run_essentia=True, dry_run=False)
    mock_snapshot.assert_any_call(ANY, flac_path, run_essentia=False, dry_run=True)
    mock_transcode.assert_called_once()
    assert row is not None
    assert row[0] == str(mp3_path)
