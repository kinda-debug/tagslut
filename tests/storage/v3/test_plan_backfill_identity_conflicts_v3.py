from __future__ import annotations

import csv
import importlib.util as _ilu
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

from tagslut.storage.schema import init_db

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "db" / "plan_backfill_identity_conflicts_v3.py"
_SPEC = _ilu.spec_from_file_location("plan_backfill_identity_conflicts_v3", _SCRIPT)
assert _SPEC is not None
_MOD: ModuleType = _ilu.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)

main = _MOD.main


def _fixture_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "music.db"
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO files (
                path, canonical_artist, canonical_title, canonical_isrc, duration_ref_ms, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "/music/exact-conflict.flac",
                    "DJ T.",
                    "City Life",
                    "DEBE71100012",
                    300000,
                    "{}",
                ),
                (
                    "/music/fuzzy-collision.flac",
                    None,
                    None,
                    None,
                    215000,
                    "{\"artist\":\"The Cure\",\"title\":\"Friday I'm in Love\"}",
                ),
            ],
        )
        conn.executemany(
            """
            INSERT INTO track_identity (
                identity_key, isrc, artist_norm, title_norm, duration_ref_ms,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "isrc:debe71100012-a",
                    "DEBE71100012",
                    "dj t.",
                    "city life",
                    300000,
                    "2026-01-01T00:00:00+00:00",
                    "migration",
                    "test_fixture",
                    "legacy",
                ),
                (
                    "isrc:debe71100012-b",
                    "DEBE71100012",
                    "dj t. feat. cari golden",
                    "city life (feat. cari golden) [acapella]",
                    300000,
                    "2026-01-01T00:00:00+00:00",
                    "migration",
                    "test_fixture",
                    "legacy",
                ),
                (
                    "isrc:gbalb9200002",
                    "GBALB9200002",
                    "the cure",
                    "friday i'm in love",
                    215160,
                    "2026-01-01T00:00:00+00:00",
                    "migration",
                    "test_fixture",
                    "legacy",
                ),
                (
                    "isrc:gbalb9200003",
                    "GBALB9200003",
                    "the cure",
                    "friday i'm in love",
                    214400,
                    "2026-01-01T00:00:00+00:00",
                    "migration",
                    "test_fixture",
                    "legacy",
                ),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_plan_backfill_identity_conflicts_writes_full_plan(tmp_path: Path) -> None:
    db_path = _fixture_db(tmp_path)
    out_csv = tmp_path / "plan.csv"
    out_json = tmp_path / "plan.json"

    rc = main(
        [
            "--db",
            str(db_path),
            "--out-csv",
            str(out_csv),
            "--out-json",
            str(out_json),
        ]
    )

    assert rc == 0
    rows = list(csv.DictReader(out_csv.open("r", encoding="utf-8")))
    payload = json.loads(out_json.read_text(encoding="utf-8"))

    assert len(rows) == 2
    assert payload["total_rows"] == 2
    assert payload["issue_counts"] == {
        "exact_conflict": 1,
        "fuzzy_collision": 1,
    }
    actions = {row["suggested_action"] for row in rows}
    assert "manual_review_variant_metadata" in actions
    assert "manual_review_distinct_exact_ids" in actions
