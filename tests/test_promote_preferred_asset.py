"""Tests for preferred-asset-aware selection in promote_replace_merge."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.storage.v3.schema import create_schema_v3
from tools.review.promote_replace_merge import plan_promote_assets_for_root


def _create_v3_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, merged_into_id) VALUES (?, ?, NULL)",
            [
                (1, "id:one"),
                (2, "id:two"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [
                (11, "/root/a.flac"),
                (12, "/root/b.flac"),
                (13, "/other/c.flac"),
                (21, "/root/c.flac"),
                (22, "/root/d.flac"),
            ],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, ?, 1)",
            [
                (11, 1),
                (12, 1),
                (13, 1),
                (21, 2),
                (22, 2),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_preferred_under_root_selects_only_preferred_asset(tmp_path: Path) -> None:
    db = _create_v3_fixture(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            (1, 12, 1.0, "{}", 1),
        )
        conn.commit()

        selected, stats = plan_promote_assets_for_root(
            conn,
            root=Path("/root"),
            use_preferred_asset=True,
            require_preferred_asset=False,
            allow_multiple_per_identity=False,
        )
    finally:
        conn.close()

    assert "/root/b.flac" in selected
    assert selected["/root/b.flac"]["asset_id"] == 12
    assert selected["/root/b.flac"]["selection_reason"] == "preferred_under_root"
    assert not ("/root/a.flac" in selected and selected["/root/a.flac"]["identity_id"] == 1)
    assert stats["identities_scanned"] == 2


def test_preferred_outside_root_falls_back_under_root_and_records_reason(tmp_path: Path) -> None:
    db = _create_v3_fixture(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(
            "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, ?, ?, ?)",
            (1, 13, 1.0, "{}", 1),
        )
        conn.commit()

        selected, _ = plan_promote_assets_for_root(
            conn,
            root=Path("/root"),
            use_preferred_asset=True,
            require_preferred_asset=False,
            allow_multiple_per_identity=False,
        )
    finally:
        conn.close()

    # Deterministic fallback: lexicographically smallest under-root path.
    assert selected["/root/a.flac"]["asset_id"] == 11
    assert selected["/root/a.flac"]["selection_reason"] == "preferred_outside_root"


def test_absent_preferred_asset_table_uses_legacy_fallback_selection(tmp_path: Path) -> None:
    db = tmp_path / "music_v3_no_preferred.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(
            """
            CREATE TABLE track_identity (
                id INTEGER PRIMARY KEY,
                identity_key TEXT NOT NULL,
                merged_into_id INTEGER
            );
            CREATE TABLE asset_file (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL
            );
            CREATE TABLE asset_link (
                id INTEGER PRIMARY KEY,
                asset_id INTEGER NOT NULL,
                identity_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.execute("INSERT INTO track_identity (id, identity_key, merged_into_id) VALUES (1, 'id:one', NULL)")
        conn.executemany(
            "INSERT INTO asset_file (id, path) VALUES (?, ?)",
            [(11, "/root/z.flac"), (12, "/root/a.flac")],
        )
        conn.executemany(
            "INSERT INTO asset_link (asset_id, identity_id, active) VALUES (?, 1, 1)",
            [(11,), (12,)],
        )
        conn.commit()

        selected, stats = plan_promote_assets_for_root(
            conn,
            root=Path("/root"),
            use_preferred_asset=True,
            require_preferred_asset=False,
            allow_multiple_per_identity=False,
        )
    finally:
        conn.close()

    assert selected["/root/a.flac"]["asset_id"] == 12
    assert selected["/root/a.flac"]["selection_reason"] == "preferred_table_missing"
    assert stats["selected"] == 1
