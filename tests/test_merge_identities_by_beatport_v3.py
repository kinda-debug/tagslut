"""Tests for beatport duplicate identity merge planning/execution."""

from __future__ import annotations

import csv
import importlib.util as _ilu
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from tagslut.db.v3.merge_identities import (
    choose_winner_identity,
    find_duplicate_beatport_groups,
    merge_group_by_repointing_assets,
)
from tagslut.db.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "db" / "merge_identities_by_beatport_v3.py"

_SPEC = _ilu.spec_from_file_location("merge_identities_by_beatport_v3", SCRIPT_PATH)
_SCRIPT_MOD = _ilu.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SCRIPT_MOD)


def _create_case1_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
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
                enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
                beatport_id
            ) VALUES (?, ?, ?)
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
    assert int(merge_log_count) == 1
    assert int(prov_count) == 1


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
