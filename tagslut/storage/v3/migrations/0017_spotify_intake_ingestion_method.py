"""Migration 0017: allow spotify_intake in track_identity.ingestion_method."""

from __future__ import annotations

import re
import sqlite3

from tagslut.storage.v3.schema import create_schema_v3

VERSION = 17


def _quote_ident(name: str) -> str:
    return f'"{name.replace("\"", "\"\"")}"'


def up(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'track_identity'"
    ).fetchone()
    if row is None or not row[0]:
        raise RuntimeError("track_identity table definition not found")

    create_sql = str(row[0])
    if "'spotify_intake'" in create_sql:
        return
    if "'multi_provider_reconcile'" not in create_sql:
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
        "'multi_provider_reconcile'",
        "'multi_provider_reconcile',\n                    'spotify_intake'",
        1,
    )

    columns = [str(column[1]) for column in conn.execute("PRAGMA table_info(track_identity)").fetchall()]
    if not columns:
        raise RuntimeError("track_identity has no columns")
    column_list = ", ".join(_quote_ident(column) for column in columns)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS track_identity_new")
        conn.execute(new_create_sql)
        conn.execute(
            f"INSERT INTO track_identity_new ({column_list}) SELECT {column_list} FROM track_identity"
        )
        conn.execute("DROP TABLE track_identity")
        conn.execute("ALTER TABLE track_identity_new RENAME TO track_identity")
        create_schema_v3(conn)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
