from __future__ import annotations

import csv
import importlib.util
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "resolve_unresolved.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("resolve_unresolved", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY,
                isrc TEXT,
                artist_norm TEXT,
                title_norm TEXT,
                album_norm TEXT,
                canonical_title TEXT,
                canonical_artist TEXT,
                canonical_album TEXT,
                canonical_year INTEGER,
                canonical_release_date TEXT,
                canonical_payload_json TEXT,
                merged_into_id INTEGER
            );

            CREATE TABLE asset_file (
                id INTEGER PRIMARY KEY,
                path TEXT,
                zone TEXT,
                library TEXT
            );

            CREATE TABLE asset_link (
                asset_id INTEGER,
                identity_id INTEGER,
                active INTEGER,
                link_source TEXT,
                confidence REAL
            );

            CREATE TABLE provenance_event (
                event_type TEXT,
                asset_id INTEGER,
                identity_id INTEGER,
                source_path TEXT,
                dest_path TEXT,
                status TEXT,
                ingestion_method TEXT,
                details_json TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO track_identity (
                id,
                artist_norm,
                title_norm,
                album_norm,
                canonical_title,
                canonical_artist,
                canonical_album,
                canonical_year,
                merged_into_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "example artist",
                "example title",
                "example album",
                "Example Title",
                "Example Artist",
                "Example Album",
                2024,
                None,
            ),
        )
        conn.commit()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _prepare_logs(logs_root: Path) -> None:
    logs_root.mkdir()
    (logs_root / "inventory_20260414_000000.tsv").write_text("", encoding="utf-8")
    (logs_root / "intake_sweep_20260414_000000.tsv").write_text("", encoding="utf-8")


def test_exact_fuzzy_match_is_auto_moved_in_dry_run(tmp_path, monkeypatch) -> None:
    module = _load_module()

    db_path = tmp_path / "music.db"
    logs_root = tmp_path / "logs"
    master_root = tmp_path / "MASTER_LIBRARY"
    src = tmp_path / "orphan.flac"

    _create_db(db_path)
    _prepare_logs(logs_root)
    src.touch()

    monkeypatch.setattr(module, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(module, "MASTER_ROOT", master_root)
    monkeypatch.setattr(module, "_iter_unresolved_flacs", lambda: [src])
    monkeypatch.setattr(
        module,
        "_read_file_tags",
        lambda _path: module.FileTags(
            isrc="",
            artist="Example Artist",
            title="Example Title",
            album="",
            year="",
            disc=1,
            track=1,
        ),
    )
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--db", str(db_path), "--dry-run"])

    rc = module.main()

    assert rc == 0

    report_path = next(logs_root.glob("resolve_unresolved_*.tsv"))
    rows = _read_rows(report_path)

    assert len(rows) == 1
    assert rows[0]["result"] == "moved"
    assert rows[0]["match_method"] == "fuzzy"
    assert rows[0]["target_path"] == str(
        master_root / "Example Artist" / "(2024) Example Album" / "1-01. Example Title - Example Artist.flac"
    )
    assert "score=1.000" in rows[0]["notes"]
    assert "auto_fuzzy_exact" in rows[0]["notes"]
    assert "dry_run" in rows[0]["notes"]


def test_non_exact_fuzzy_match_stays_pending_review(tmp_path, monkeypatch) -> None:
    module = _load_module()

    db_path = tmp_path / "music.db"
    logs_root = tmp_path / "logs"
    master_root = tmp_path / "MASTER_LIBRARY"
    src = tmp_path / "orphan.flac"

    _create_db(db_path)
    _prepare_logs(logs_root)
    src.touch()

    monkeypatch.setattr(module, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(module, "MASTER_ROOT", master_root)
    monkeypatch.setattr(module, "_iter_unresolved_flacs", lambda: [src])
    monkeypatch.setattr(
        module,
        "_read_file_tags",
        lambda _path: module.FileTags(
            isrc="",
            artist="Example Artist",
            title="Example Title",
            album="",
            year="",
            disc=1,
            track=1,
        ),
    )
    monkeypatch.setattr(module, "_best_fuzzy_match", lambda *_args, **_kwargs: (1, 0.976, False))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--db", str(db_path), "--dry-run"])

    rc = module.main()

    assert rc == 0

    report_path = next(logs_root.glob("resolve_unresolved_*.tsv"))
    rows = _read_rows(report_path)

    assert len(rows) == 1
    assert rows[0]["result"] == "fuzzy_match_pending_review"
    assert rows[0]["match_method"] == "fuzzy"
    assert rows[0]["target_path"] == ""
    assert rows[0]["notes"] == "score=0.976"
