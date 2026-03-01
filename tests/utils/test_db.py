import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.schema import init_db
from tagslut.utils.db import DbResolution, DbResolutionError, open_db, resolve_db_path


class DummyConfig:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self.values = values or {}

    def get(self, key: str, default: object = None) -> object:
        return self.values.get(key, default)


def test_resolve_db_path_prefers_cli_over_env_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_db = tmp_path / "env.db"
    config_db = tmp_path / "config.db"
    cli_db = tmp_path / "cli.db"
    monkeypatch.setenv("TAGSLUT_DB", str(env_db))

    resolution = resolve_db_path(
        cli_db=cli_db,
        config=DummyConfig({"db.path": str(config_db)}),  # type: ignore[arg-type]
        allow_repo_db=True,
        purpose="write",
        allow_create=True,
        require=True,
    )

    assert resolution.source == "cli"
    assert resolution.path == cli_db


def test_resolve_db_path_read_mode_requires_existing_db(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"

    with pytest.raises(DbResolutionError, match="Database does not exist"):
        resolve_db_path(
            cli_db=missing,
            config=DummyConfig(),  # type: ignore[arg-type]
            allow_repo_db=True,
            purpose="read",
            require=True,
        )


def test_open_db_creates_writable_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "created.db"
    resolution = DbResolution(
        path=db_path,
        source="cli",
        candidates=[("cli", str(db_path))],
        exists=False,
        purpose="write",
        allow_create=True,
        allow_repo_db=True,
        repo_root=tmp_path,
    )

    conn = open_db(resolution)
    try:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES (?)", ("ok",))
        row = conn.execute("SELECT name FROM sample").fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["name"] == "ok"


def test_init_db_records_schema_versions(tmp_path: Path) -> None:
    db_path = tmp_path / "schema.db"
    conn = sqlite3.connect(db_path)
    try:
        init_db(conn)
        rows = conn.execute(
            "SELECT schema_name FROM schema_migrations"
        ).fetchall()
    finally:
        conn.close()

    names = {row[0] for row in rows}
    assert "integrity" in names
    assert "v3" in names
