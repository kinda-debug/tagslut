"""Database integration for Audio Suite.

This module provides functions to construct a SQLAlchemy engine, define ORM
models and perform simple operations such as scanning a music library and
initialising the schema.  Actual audio metadata extraction is deferred to
external libraries; here we simply record the file paths and basic tags.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import declarative_base

from .config import get_settings

Base = declarative_base()


class Track(Base):
    """Simple ORM model representing a FLAC track in the local library."""

    __tablename__ = "tracks"

    # SQLAlchemy will automatically generate an integer primary key called id
    id: int | None = None  # type: ignore[assignment]
    path: str | None = None  # type: ignore[assignment]
    artist: str | None = None  # type: ignore[assignment]
    album: str | None = None  # type: ignore[assignment]
    title: str | None = None  # type: ignore[assignment]
    duration: int | None = None  # type: ignore[assignment]

    from sqlalchemy import Column, Integer, String

    id = Column(Integer, primary_key=True, autoincrement=True)
    path = Column(String, unique=True, nullable=False)
    artist = Column(String, nullable=True)
    album = Column(String, nullable=True)
    title = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)


def get_engine(settings: None = None) -> Engine:
    """Construct a SQLAlchemy engine based on the configured database path."""
    settings = settings or get_settings()
    db_path = Path(os.path.expanduser(settings.get("db_path")))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    return engine


def initialise_database(engine: Engine) -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = Session(engine, autoflush=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def scan_music(engine: Engine, roots: Iterable[str], force: bool = False) -> None:
    """Walk through the given directories and index FLAC files.

    This implementation is intentionally naive: it treats any file with
    a ``.flac`` extension as a track and records its absolute path.  If
    ``force`` is False, already indexed paths are skipped.  Metadata
    extraction (artist, album, title, duration) is left unimplemented for
    brevity; all fields remain None.
    """
    paths = [Path(os.path.expanduser(p)).resolve() for p in roots if p]
    for root in paths:
        if not root.exists():
            continue
        for flac_path in root.rglob("*.flac"):
            with session_scope(engine) as session:
                # Skip if track already exists unless forcing reindex
                exists = session.scalar(select(Track).where(Track.path == str(flac_path)))
                if exists and not force:
                    continue
                if exists:
                    session.delete(exists)
                session.add(Track(path=str(flac_path)))