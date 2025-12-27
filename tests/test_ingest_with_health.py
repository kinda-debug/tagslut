from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tools import manual_ingest


TEST_DATA = Path(__file__).parent / "data"


def _create_db(path: Path) -> sqlite3.Connection:
    columns_sql = ", ".join(f"{col} TEXT" for col in manual_ingest.LIBRARY_COLUMNS)
    connection = sqlite3.connect(path)
    connection.execute(f"CREATE TABLE library_files ({columns_sql})")
    connection.row_factory = sqlite3.Row
    return connection


def test_ingest_stores_health_score(tmp_path: Path) -> None:
    db_path = tmp_path / "library.db"
    with _create_db(db_path) as conn:
        manual_ingest.ingest_paths(conn, [str(TEST_DATA / "healthy.flac")])
        row = conn.execute("SELECT extra_json FROM library_files").fetchone()

    payload = json.loads(row["extra_json"])
    assert "health_score" in payload
    assert payload["health_score"] > 0


def test_ingest_handles_corrupt_files(tmp_path: Path) -> None:
    db_path = tmp_path / "library.db"
    corrupt = TEST_DATA / "corrupt.flac"
    healthy = TEST_DATA / "healthy.flac"

    with _create_db(db_path) as conn:
        manual_ingest.ingest_paths(
            conn,
            [str(corrupt), str(healthy)],
        )
        rows = conn.execute(
            "SELECT path, extra_json FROM library_files ORDER BY path"
        ).fetchall()

    assert len(rows) == 2
    corrupt_row = next(row for row in rows if row["path"].endswith("corrupt.flac"))
    payload = json.loads(corrupt_row["extra_json"])
    assert payload.get("health_score") == 0
    assert "error" in payload
