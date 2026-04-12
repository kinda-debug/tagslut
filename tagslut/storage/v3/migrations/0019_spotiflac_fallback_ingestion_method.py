"""Migration 0019: allow spotiflac_fallback in track_identity.ingestion_method."""

from __future__ import annotations

import re
import sqlite3

from tagslut.storage.v3.schema import create_schema_v3

VERSION = 19


def _quote_ident(name: str) -> str:
    return f"\"{name.replace('\"', '\"\"')}\""


def _collect_views(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'view' AND sql IS NOT NULL"
    ).fetchall()
    views: list[tuple[str, str]] = []
    for name, sql in rows:
        view_name = str(name) if name is not None else ""
        view_sql = str(sql) if sql is not None else ""
        if view_name and view_sql:
            views.append((view_name, view_sql))
    return views


def _create_view_if_missing(conn: sqlite3.Connection, create_sql: str) -> None:
    sql = create_sql.strip()
    if not sql:
        return
    if re.match(r"^CREATE\s+VIEW\s+IF\s+NOT\s+EXISTS\s+", sql, flags=re.IGNORECASE):
        conn.execute(sql)
        return
    sql = re.sub(
        r"^CREATE\s+VIEW\s+",
        "CREATE VIEW IF NOT EXISTS ",
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
    conn.execute(sql)


def up(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'track_identity'"
    ).fetchone()
    if row is None or not row[0]:
        raise RuntimeError("track_identity table definition not found")

    create_sql = str(row[0])
    if "'spotiflac_fallback'" in create_sql:
        return
    if "'spotify_intake'" not in create_sql:
        raise RuntimeError("track_identity ingestion_method CHECK does not match expected shape")

    new_create_sql = re.sub(
        r"^CREATE TABLE(?: IF NOT EXISTS)? track_identity\b",
        "CREATE TABLE track_identity_new",
        create_sql,
        count=1,
    )
    if new_create_sql == create_sql:
        raise RuntimeError("could not rewrite track_identity CREATE TABLE statement")
    new_create_sql = new_create_sql.replace(
        "'spotify_intake'",
        "'spotify_intake',\n                    'spotiflac_fallback'",
        1,
    )

    columns = [str(column[1]) for column in conn.execute("PRAGMA table_info(track_identity)").fetchall()]
    if not columns:
        raise RuntimeError("track_identity has no columns")
    column_list = ", ".join(_quote_ident(column) for column in columns)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        existing_views = _collect_views(conn)
        for view_name, _view_sql in existing_views:
            conn.execute(f"DROP VIEW IF EXISTS {_quote_ident(view_name)}")

        conn.execute("DROP TABLE IF EXISTS track_identity_new")
        conn.execute(new_create_sql)
        conn.execute(
            f"INSERT INTO track_identity_new ({column_list}) SELECT {column_list} FROM track_identity"
        )
        conn.execute("DROP TABLE track_identity")
        conn.execute("ALTER TABLE track_identity_new RENAME TO track_identity")
        create_schema_v3(conn)
        for _view_name, view_sql in existing_views:
            _create_view_if_missing(conn, view_sql)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

