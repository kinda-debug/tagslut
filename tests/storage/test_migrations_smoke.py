"""Smoke tests for the tagslut.migrations submodule."""

import sqlite3

import tagslut.migrations.migrate_checksum_provenance as migrations_mod
from tagslut.migrations.migrate_checksum_provenance import ChecksumProvenanceMigration


def test_migration_module_importable() -> None:
    assert hasattr(migrations_mod, "ChecksumProvenanceMigration")


def test_infer_checksum_type_streaminfo() -> None:
    result = ChecksumProvenanceMigration.infer_checksum_type({"streaminfo_md5": "abc"})
    assert result == "STREAMINFO"


def test_infer_checksum_type_sha256() -> None:
    result = ChecksumProvenanceMigration.infer_checksum_type({"sha256": "deadbeef"})
    assert result == "SHA256"


def test_infer_checksum_type_unknown() -> None:
    result = ChecksumProvenanceMigration.infer_checksum_type({})
    assert result == "UNKNOWN"


def test_get_pending_migrations_empty_table() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE files (id INTEGER PRIMARY KEY, checksum_type TEXT)"
    )
    pending = ChecksumProvenanceMigration.get_pending_migrations(conn)
    assert pending == 0
    conn.close()


def test_migrate_rows_updates_checksum_type() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY,
            checksum_type TEXT,
            streaminfo_md5 TEXT,
            sha256 TEXT,
            md5 TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO files (id, streaminfo_md5, sha256, md5) VALUES (1, 'abc', NULL, NULL)"
    )
    conn.commit()

    count = ChecksumProvenanceMigration.migrate_rows(conn)
    assert count == 1

    row = conn.execute("SELECT checksum_type FROM files WHERE id = 1").fetchone()
    assert row[0] == "STREAMINFO"
    conn.close()
