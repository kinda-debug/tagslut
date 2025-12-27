"""Module description placeholder."""

from __future__ import annotations

from pathlib import Path

from dedupe import matcher, scanner, utils


RECOVERED_TABLE = "recovered_files"


def _create_library_db(path: Path) -> None:
    context = utils.DatabaseContext(path)
    with context.connect() as connection:
        scanner.initialise_database(connection)
        library_path = utils.normalise_path("/music/foo.flac")
        connection.execute(
            (
                f"INSERT INTO {scanner.LIBRARY_TABLE} "
                "(path, size_bytes, mtime, checksum) VALUES (?, ?, ?, ?)"
            ),
            (library_path, 1000, 0, "deadbeef"),
        )


def _create_recovered_db(path: Path) -> None:
    context = utils.DatabaseContext(path)
    with context.connect() as connection:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {RECOVERED_TABLE} (
                source_path TEXT PRIMARY KEY,
                suggested_name TEXT,
                size_bytes INTEGER,
                extension TEXT
            )
            """
        )
        recovered_path = utils.normalise_path("/recover/foo.flac")
        connection.execute(
            (
                f"INSERT INTO {RECOVERED_TABLE} "
                "(source_path, suggested_name, size_bytes, extension) "
                "VALUES (?, ?, ?, ?)"
            ),
            (recovered_path, "foo.flac", 995, "flac"),
        )


def test_match_databases_emits_matches_csv(tmp_path: Path) -> None:
    library_db = tmp_path / "library.db"
    recovered_db = tmp_path / "recovered.db"
    matches_csv = tmp_path / "matches.csv"
    _create_library_db(library_db)
    _create_recovered_db(recovered_db)

    matches = matcher.match_databases(library_db, recovered_db, matches_csv)
    assert any(
        match.classification != "missing" for match in matches if match.library_path
    )
    assert matches_csv.exists()


def test_matcher_normalises_loaded_paths(tmp_path: Path) -> None:
    library_db = tmp_path / "library.db"
    recovered_db = tmp_path / "recovered.db"
    _create_library_db(library_db)
    _create_recovered_db(recovered_db)

    library_entries = matcher.load_library_entries(library_db)
    recovery_entries = matcher.load_recovery_entries(recovered_db)

    assert all(
        utils.normalise_path(entry.path) == entry.path for entry in library_entries
    )
    assert all(
        utils.normalise_path(entry.source_path) == entry.source_path
        for entry in recovery_entries
    )
