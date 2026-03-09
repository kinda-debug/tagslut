from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

from tagslut.exec.canonical_writeback import CanonicalWritebackStats

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_post_move_module():
    module_path = PROJECT_ROOT / "tools" / "review" / "post_move_enrich_art.py"
    spec = importlib.util.spec_from_file_location("post_move_enrich_art_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeEnricher:
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False

    def enrich_file(self, _path: str, *, force: bool, retry_no_match: bool):  # type: ignore[no-untyped-def]
        return None, "enriched"


def _make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "music.db"
    sqlite3.connect(str(db_path)).close()
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")
    paths_file = tmp_path / "paths.txt"
    paths_file.write_text(f"{flac_path}\n", encoding="utf-8")
    return db_path, paths_file


def test_post_move_enrich_art_defaults_writeback_force_false(tmp_path: Path) -> None:
    module = _load_post_move_module()
    db_path, paths_file = _make_inputs(tmp_path)
    captured: dict[str, object] = {}

    def _fake_writeback(conn, sources, *, force, execute, echo):  # type: ignore[no-untyped-def]
        captured["force"] = force
        captured["execute"] = execute
        captured["sources"] = list(sources)
        return CanonicalWritebackStats(scanned=1, updated=0, skipped=1, missing=0)

    module.parse_args = lambda: argparse.Namespace(  # type: ignore[assignment]
        db=str(db_path),
        paths_file=str(paths_file),
        providers="beatport",
        force=False,
        retry_no_match=False,
        art_force=False,
        skip_art=True,
        writeback_force=False,
    )
    module.TokenManager = lambda: object()  # type: ignore[assignment]
    module.Enricher = _FakeEnricher  # type: ignore[assignment]
    module.write_canonical_tags = _fake_writeback  # type: ignore[assignment]
    module.logging.basicConfig = lambda *args, **kwargs: None  # type: ignore[assignment]

    result = module.main()

    assert result == 0
    assert captured["force"] is False
    assert captured["execute"] is True


def test_post_move_enrich_art_writeback_force_flag_sets_force_true(tmp_path: Path) -> None:
    module = _load_post_move_module()
    db_path, paths_file = _make_inputs(tmp_path)
    captured: dict[str, object] = {}

    def _fake_writeback(conn, sources, *, force, execute, echo):  # type: ignore[no-untyped-def]
        captured["force"] = force
        return CanonicalWritebackStats(scanned=1, updated=1, skipped=0, missing=0)

    module.parse_args = lambda: argparse.Namespace(  # type: ignore[assignment]
        db=str(db_path),
        paths_file=str(paths_file),
        providers="beatport",
        force=False,
        retry_no_match=False,
        art_force=False,
        skip_art=True,
        writeback_force=True,
    )
    module.TokenManager = lambda: object()  # type: ignore[assignment]
    module.Enricher = _FakeEnricher  # type: ignore[assignment]
    module.write_canonical_tags = _fake_writeback  # type: ignore[assignment]
    module.logging.basicConfig = lambda *args, **kwargs: None  # type: ignore[assignment]

    result = module.main()

    assert result == 0
    assert captured["force"] is True


def test_post_move_enrich_art_parse_args_rejects_removed_dj_map_file(monkeypatch, tmp_path: Path) -> None:
    module = _load_post_move_module()
    db_path, paths_file = _make_inputs(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "post_move_enrich_art.py",
            "--db",
            str(db_path),
            "--paths-file",
            str(paths_file),
            "--dj-map-file",
            str(tmp_path / "dj-map.tsv"),
        ],
    )

    try:
        module.parse_args()
        assert False, "expected argparse failure for removed --dj-map-file"
    except SystemExit as exc:
        assert int(exc.code) == 2
