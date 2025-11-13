from __future__ import annotations

from pathlib import Path

from dedupe import matcher, rstudio_parser, scanner, utils


def _create_library_db(path: Path) -> None:
    context = utils.DatabaseContext(path)
    with context.connect() as connection:
        scanner.initialise_database(connection)
        connection.execute(
            f"INSERT INTO {scanner.LIBRARY_TABLE} (path, size_bytes, mtime, checksum) VALUES (?, ?, ?, ?)",
            ("/music/foo.flac", 1000, 0, "deadbeef"),
        )


def _create_recovered_db(path: Path) -> None:
    context = utils.DatabaseContext(path)
    with context.connect() as connection:
        rstudio_parser.initialise_database(connection)
        connection.execute(
            f"INSERT INTO {rstudio_parser.RECOVERED_TABLE} (source_path, suggested_name, size_bytes, extension) VALUES (?, ?, ?, ?)",
            ("/recover/foo.flac", "foo.flac", 995, "flac"),
        )


def test_match_databases_generates_rows(tmp_path: Path) -> None:
    library_db = tmp_path / "library.db"
    recovered_db = tmp_path / "recovered.db"
    matches_csv = tmp_path / "matches.csv"
    _create_library_db(library_db)
    _create_recovered_db(recovered_db)

    matches = matcher.match_databases(library_db, recovered_db, matches_csv)
    assert any(match.classification != "missing" for match in matches if match.library_path)
    assert matches_csv.exists()
