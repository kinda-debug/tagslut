from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import create_schema_v3

RELEVANT_TABLES = (
    "asset_file",
    "asset_link",
    "dj_validation_state",
    "preferred_asset",
    "schema_migrations",
    "track_identity",
)
PROVIDER_UNIQUE_INDEXES = (
    "uq_track_identity_active_apple_music_id",
    "uq_track_identity_active_beatport_id",
    "uq_track_identity_active_deezer_id",
    "uq_track_identity_active_qobuz_id",
    "uq_track_identity_active_spotify_id",
    "uq_track_identity_active_tidal_id",
    "uq_track_identity_active_traxsource_id",
)
RELEVANT_INDEXES = PROVIDER_UNIQUE_INDEXES


def _normalize_sql(sql: str | None) -> str | None:
    if sql is None:
        return None
    return " ".join(sql.split())


def _sqlite_master_rows(conn: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    names = (*RELEVANT_TABLES, *RELEVANT_INDEXES)
    placeholders = ", ".join("?" for _ in names)
    rows = conn.execute(
        f"""
        SELECT type, name, sql
        FROM sqlite_master
        WHERE name IN ({placeholders})
        ORDER BY type, name
        """,
        names,
    ).fetchall()
    return [(str(row[0]), str(row[1]), _normalize_sql(row[2])) for row in rows]


def _index_list(conn: sqlite3.Connection, table: str) -> list[tuple[str, int, str, int]]:
    rows = conn.execute(f"PRAGMA index_list({table})").fetchall()
    normalized = [
        (str(row[1]), int(row[2]), str(row[3]), int(row[4]))
        for row in rows
        if str(row[1]) in RELEVANT_INDEXES
    ]
    return sorted(normalized, key=lambda row: row[0])


def _index_xinfo(conn: sqlite3.Connection, index_name: str) -> list[tuple[int, int, str | None, int, str, int]]:
    rows = conn.execute(f"PRAGMA index_xinfo({index_name})").fetchall()
    return [
        (
            int(row[0]),
            int(row[1]),
            None if row[2] is None else str(row[2]),
            int(row[3]),
            str(row[4]),
            int(row[5]),
        )
        for row in rows
    ]


def _schema_migrations_rows(conn: sqlite3.Connection) -> list[tuple[str, int, str | None]]:
    rows = conn.execute(
        """
        SELECT schema_name, version, note
        FROM schema_migrations
        WHERE schema_name = 'v3'
        ORDER BY version
        """
    ).fetchall()
    return [(str(row[0]), int(row[1]), None if row[2] is None else str(row[2])) for row in rows]


def _make_fresh_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        create_schema_v3(conn)
    finally:
        conn.close()


def _make_upgrade_db(path: Path, migrations_dir: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        create_schema_v3(conn)
        conn.execute(
            """
            DELETE FROM schema_migrations
            WHERE schema_name = 'v3' AND version IN (10, 11, 12, 14)
            """
        )
        conn.execute("DROP TABLE IF EXISTS dj_validation_state")
        for index_name in PROVIDER_UNIQUE_INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {index_name}")
        conn.execute("DROP INDEX IF EXISTS idx_track_identity_ingested_at")
        conn.execute("DROP INDEX IF EXISTS idx_track_identity_ingestion_method")
        conn.execute("DROP INDEX IF EXISTS idx_track_identity_ingestion_confidence")
        conn.execute("DROP TRIGGER IF EXISTS trg_track_identity_provenance_required")
        conn.commit()
    finally:
        conn.close()

    applied = run_pending_v3(path, migrations_dir=migrations_dir)
    assert applied == [
        "0010_track_identity_provider_uniqueness.py",
        "0011_track_identity_provider_uniqueness_hardening.py",
        "0012_ingestion_provenance.py",
        "0014_dj_validation_state.py",
    ]


def test_fresh_create_schema_v3_matches_v11_upgrade_path_for_effective_schema(
    tmp_path: Path,
) -> None:
    source_dir = Path(__file__).resolve().parents[3] / "tagslut" / "storage" / "v3" / "migrations"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    for filename in (
        "0010_track_identity_provider_uniqueness.py",
        "0011_track_identity_provider_uniqueness_hardening.py",
        "0012_ingestion_provenance.py",
        "0014_dj_validation_state.py",
    ):
        shutil.copy2(source_dir / filename, migrations_dir / filename)

    fresh_db = tmp_path / "fresh.sqlite"
    upgrade_db = tmp_path / "upgrade.sqlite"
    _make_fresh_db(fresh_db)
    _make_upgrade_db(upgrade_db, migrations_dir)

    fresh = sqlite3.connect(fresh_db)
    upgrade = sqlite3.connect(upgrade_db)
    try:
        fresh_master = _sqlite_master_rows(fresh)
        upgrade_master = _sqlite_master_rows(upgrade)
        assert fresh_master == upgrade_master, (
            "sqlite_master mismatch\n"
            f"fresh={fresh_master}\n"
            f"upgrade={upgrade_master}"
        )

        fresh_index_list = _index_list(fresh, "track_identity")
        upgrade_index_list = _index_list(upgrade, "track_identity")
        assert fresh_index_list == upgrade_index_list, (
            "PRAGMA index_list(track_identity) mismatch\n"
            f"fresh={fresh_index_list}\n"
            f"upgrade={upgrade_index_list}"
        )

        for index_name in PROVIDER_UNIQUE_INDEXES:
            fresh_xinfo = _index_xinfo(fresh, index_name)
            upgrade_xinfo = _index_xinfo(upgrade, index_name)
            assert fresh_xinfo == upgrade_xinfo, (
                f"PRAGMA index_xinfo({index_name}) mismatch\n"
                f"fresh={fresh_xinfo}\n"
                f"upgrade={upgrade_xinfo}"
            )

        fresh_migrations = _schema_migrations_rows(fresh)
        upgrade_migrations = _schema_migrations_rows(upgrade)
        assert fresh_migrations == upgrade_migrations, (
            "schema_migrations mismatch\n"
            f"fresh={fresh_migrations}\n"
            f"upgrade={upgrade_migrations}"
        )
    finally:
        fresh.close()
        upgrade.close()
