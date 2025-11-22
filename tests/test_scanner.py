from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path

from dedupe import scanner, utils


def _stub_prepare_record(path: Path, include_fingerprints: bool) -> scanner.ScanRecord:
    """Return a lightweight :class:`ScanRecord` without external tooling."""

    stat = path.stat()
    return scanner.ScanRecord(
        path=utils.normalise_path(str(path)),
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        checksum="checksum",
        duration=None,
        sample_rate=None,
        bit_rate=None,
        channels=None,
        bit_depth=None,
        tags_json=json.dumps({"name": path.name}, sort_keys=True, separators=(",", ":")),
        fingerprint=None,
        fingerprint_duration=None,
    )


def _initialise_db(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    scanner.initialise_database(connection)
    return connection


def test_resume_skips_only_unchanged(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scanner, "prepare_record", _stub_prepare_record)

    root = tmp_path / "library"
    root.mkdir()

    unchanged = root / "Cafe\u0301.flac"
    unchanged.write_bytes(b"a")
    fresh = root / "fresh.flac"
    fresh.write_bytes(b"b")

    database = tmp_path / "library.db"
    with _initialise_db(database) as connection:
        scanner._upsert_batch(connection, [_stub_prepare_record(unchanged, False)])

    config = scanner.ScanConfig(
        root=root,
        database=database,
        include_fingerprints=False,
        batch_size=10,
        resume=True,
        resume_safe=False,
        show_progress=False,
    )

    processed = scanner.scan_library(config)
    assert processed == 1

    with _initialise_db(database) as connection:
        rows = connection.execute("SELECT path FROM library_files").fetchall()
    assert len(rows) == 2
    assert all(unicodedata.is_normalized("NFC", row["path"]) for row in rows)
    expected = {
        utils.normalise_path(str(unchanged)),
        utils.normalise_path(str(fresh)),
    }
    assert {row["path"] for row in rows} == expected


def test_resume_safe_skips_batch_on_match(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scanner, "prepare_record", _stub_prepare_record)

    root = tmp_path / "library"
    root.mkdir()

    unchanged = root / "song.flac"
    unchanged.write_bytes(b"a")
    second = root / "other.flac"
    second.write_bytes(b"b")

    database = tmp_path / "library.db"
    with _initialise_db(database) as connection:
        scanner._upsert_batch(connection, [_stub_prepare_record(unchanged, False)])

    config = scanner.ScanConfig(
        root=root,
        database=database,
        include_fingerprints=False,
        batch_size=10,
        resume=False,
        resume_safe=True,
        show_progress=False,
    )

    processed = scanner.scan_library(config)
    assert processed == 0

    with _initialise_db(database) as connection:
        rows = connection.execute("SELECT path FROM library_files").fetchall()
    assert len(rows) == 1
    assert rows[0]["path"] == utils.normalise_path(str(unchanged))
