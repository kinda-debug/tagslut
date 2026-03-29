"""Tests for beatport duplicate identity merge planning/execution."""

from __future__ import annotations

import csv
import importlib.util as _ilu
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tagslut.storage.v3.merge_identities import (
    choose_winner_identity,
    find_duplicate_beatport_groups,
    merge_group_by_repointing_assets,
)
from tagslut.storage.v3.identity_service import resolve_active_identity
from tagslut.storage.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "db" / "merge_identities_by_beatport_v3.py"

_SPEC = _ilu.spec_from_file_location("merge_identities_by_beatport_v3", SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_SCRIPT_MOD = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCRIPT_MOD)


def _create_case1_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.execute("DROP INDEX IF EXISTS uq_track_identity_active_beatport_id")
        conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [
                (1, "/music/a1.flac"),
                (2, "/music/a2.flac"),
                (3, "/music/a3.flac"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                beatport_id,
                isrc,
                canonical_artist,
                canonical_title,
                enriched_at,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            [
                (1, "isrc:AA1", "BP-1", "AA1", "Artist A", "Track A", None),
                (2, "beatport:BP-1", "BP-1", None, None, None, "2026-03-04T00:00:00Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (1, 1),
                (2, 2),
                (3, 1),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _create_tie_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_tie_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.execute("DROP INDEX IF EXISTS uq_track_identity_active_beatport_id")
        conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [
                (1, "/music/t1.flac"),
                (2, "/music/t2.flac"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO track_identity (
                id,
                identity_key,
                beatport_id,
                ingested_at,
                ingestion_method,
                ingestion_source,
                ingestion_confidence
            ) VALUES (?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            [
                (10, "beatport:BP-TIE-A", "BP-TIE"),
                (11, "beatport:BP-TIE-B", "BP-TIE"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (1, 10),
                (2, 11),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT_PATH), *args]
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_plan_mode_reports_group_and_winner_by_score(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    out = tmp_path / "plan.csv"

    proc = _run_script("--db", str(db), "--out", str(out))
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "mode: plan" in proc.stdout
    assert "groups_found: 1" in proc.stdout
    assert "groups_planned: 1" in proc.stdout
    assert "groups_merged: 0" in proc.stdout

    rows = _read_csv(out)
    assert len(rows) == 1
    row = rows[0]
    assert row["beatport_id"] == "BP-1"
    assert row["group_size"] == "2"
    assert row["winner_id"] == "2"
    assert row["assets_moved"] == "2"
    assert row["action"] == "merge"

    conn = sqlite3.connect(str(db))
    try:
        merged_into = conn.execute(
            "SELECT merged_into_id FROM track_identity WHERE id = 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert merged_into is None


def test_execute_mode_merges_repoints_and_logs(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    out = tmp_path / "plan.csv"

    proc = _run_script("--db", str(db), "--out", str(out), "--execute")
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "mode: execute" in proc.stdout
    assert "groups_merged: 1" in proc.stdout
    assert "failures: 0" in proc.stdout

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        active_dupes = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM (
                SELECT beatport_id
                FROM track_identity
                WHERE beatport_id IS NOT NULL
                  AND TRIM(beatport_id) != ''
                  AND merged_into_id IS NULL
                GROUP BY beatport_id
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()["n"]
        loser = conn.execute(
            "SELECT beatport_id, merged_into_id FROM track_identity WHERE id = 1"
        ).fetchone()
        winner = conn.execute(
            "SELECT canonical_artist, canonical_title FROM track_identity WHERE id = 2"
        ).fetchone()
        winner_assets = conn.execute(
            "SELECT COUNT(*) AS n FROM asset_link WHERE identity_id = 2"
        ).fetchone()["n"]
        loser_assets = conn.execute(
            "SELECT COUNT(*) AS n FROM asset_link WHERE identity_id = 1"
        ).fetchone()["n"]
        dup_asset_rows = conn.execute(
            """
            SELECT asset_id
            FROM asset_link
            GROUP BY asset_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        active_links_to_merged = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM asset_link al
            JOIN track_identity ti ON ti.id = al.identity_id
            WHERE al.active = 1 AND ti.merged_into_id IS NOT NULL
            """
        ).fetchone()["n"]
        merge_log_count = conn.execute(
            "SELECT COUNT(*) AS n FROM identity_merge_log"
        ).fetchone()["n"]
        prov_count = conn.execute(
            "SELECT COUNT(*) AS n FROM provenance_event WHERE event_type = 'identity_merge'"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert int(active_dupes) == 0
    assert loser["beatport_id"] is None
    assert int(loser["merged_into_id"]) == 2
    assert winner["canonical_artist"] == "Artist A"
    assert winner["canonical_title"] == "Track A"
    assert int(winner_assets) == 3
    assert int(loser_assets) == 0
    assert dup_asset_rows == []
    assert int(active_links_to_merged) == 0
    assert int(merge_log_count) == 1
    assert int(prov_count) == 1


def test_resolve_active_identity_returns_canonical_row_after_merge(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)
        conn.commit()
        canonical = resolve_active_identity(conn, "isrc:AA1")
    finally:
        conn.close()

    assert int(canonical["id"]) == 2
    assert str(canonical["identity_key"]) == "beatport:BP-1"


def test_tie_breaker_prefers_lowest_identity_id(tmp_path: Path) -> None:
    db = _create_tie_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        selection = choose_winner_identity(conn, [10, 11])
    finally:
        conn.close()

    assert selection.winner_id == 10


def test_asset_link_unique_invariant_preserved_after_direct_merge(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        groups = find_duplicate_beatport_groups(conn)
        assert len(groups) == 1
        group = groups[0]
        selection = choose_winner_identity(conn, group.identity_ids)
        losers = tuple(i for i in group.identity_ids if i != selection.winner_id)

        conn.execute("BEGIN")
        merge_group_by_repointing_assets(
            conn,
            selection.winner_id,
            losers,
            dry_run=False,
        )
        conn.commit()

        dup_asset_rows = conn.execute(
            """
            SELECT asset_id
            FROM asset_link
            GROUP BY asset_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
    finally:
        conn.close()

    assert dup_asset_rows == []


def test_merge_blocks_self_reference(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        with pytest.raises(RuntimeError, match="winner_id cannot be included in loser_ids"):
            merge_group_by_repointing_assets(conn, 1, [1], dry_run=False)
    finally:
        conn.close()


def test_merge_blocks_winner_that_is_already_merged(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("UPDATE track_identity SET merged_into_id = 2 WHERE id = 1")
        conn.commit()
        with pytest.raises(RuntimeError, match="winner identity cannot already be merged"):
            merge_group_by_repointing_assets(conn, 1, [2], dry_run=False)
    finally:
        conn.close()


def test_merge_syncs_legacy_file_keys(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("CREATE TABLE files (path TEXT PRIMARY KEY, library_track_key TEXT)")
        conn.executemany(
            "INSERT INTO files (path, library_track_key) VALUES (?, ?)",
            [
                ("/music/a1.flac", "isrc:AA1"),
                ("/music/a2.flac", "beatport:BP-1"),
                ("/music/a3.flac", "isrc:AA1"),
            ],
        )
        merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)
        conn.commit()
        rows = conn.execute(
            "SELECT path, library_track_key FROM files ORDER BY path"
        ).fetchall()
    finally:
        conn.close()

    assert [tuple(row) for row in rows] == [
        ("/music/a1.flac", "beatport:BP-1"),
        ("/music/a2.flac", "beatport:BP-1"),
        ("/music/a3.flac", "beatport:BP-1"),
    ]


def test_merge_removes_stale_loser_preferred_asset_rows(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.executemany(
            """
            INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, 1, 1.0, "{}", 1),
                (2, 2, 2.0, "{}", 1),
            ],
        )

        merge_group_by_repointing_assets(conn, 2, [1], dry_run=False)
        conn.commit()

        rows = conn.execute(
            "SELECT identity_id, asset_id FROM preferred_asset ORDER BY identity_id"
        ).fetchall()
    finally:
        conn.close()

    assert [tuple(row) for row in rows] == [(2, 2)]


def test_plan_connection_is_query_only_and_rejects_writes(tmp_path: Path) -> None:
    db = _create_case1_db(tmp_path)
    conn = _SCRIPT_MOD._connect_ro(db)
    try:
        query_only = int(conn.execute("PRAGMA query_only").fetchone()[0])
        assert query_only == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "UPDATE track_identity SET canonical_title = 'X' WHERE id = 1"
            )
    finally:
        conn.close()
