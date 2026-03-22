from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from tagslut.utils.config import get_config

from .models import Base

DEFAULT_LIBRARY_DB_URL = "sqlite:///~/.local/share/djtools/library.db"


def resolve_library_db_url(db_url: str | None = None) -> str:
    raw = db_url or str(get_config().get("library.db_url", DEFAULT_LIBRARY_DB_URL))
    if raw.startswith("sqlite:///"):
        path_part = raw[len("sqlite:///") :]
        if path_part != ":memory:":
            expanded = Path(path_part).expanduser()
            return f"sqlite:///{expanded}"
    return raw


def create_library_engine(db_url: str | None = None) -> Engine:
    resolved = resolve_library_db_url(db_url)
    if resolved.startswith("sqlite:///"):
        path_part = resolved[len("sqlite:///") :]
        if path_part != ":memory:":
            Path(path_part).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(resolved, future=True)


def create_library_session_factory(db_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=create_library_engine(db_url), expire_on_commit=False)


def ensure_library_schema(db_url: str | None = None) -> str:
    resolved = resolve_library_db_url(db_url)
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        engine = create_library_engine(resolved)
        Base.metadata.create_all(engine)
        return resolved

    config = Config()
    config.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent / "migrations"),
    )
    config.set_main_option("sqlalchemy.url", resolved)
    command.upgrade(config, "head")
    return resolved


__all__ = [
    "DEFAULT_LIBRARY_DB_URL",
    "create_library_engine",
    "create_library_session_factory",
    "ensure_library_schema",
    "resolve_library_db_url",
]
