from __future__ import annotations

import json
import logging
import sqlite3

import pytest

from tagslut.storage.v3.schema import create_schema_v3
from tagslut.storage.v3.provider_evidence import maybe_promote_qobuz_id, write_library_track_source


def _insert_identity(conn: sqlite3.Connection, identity_key: str) -> int:
    conn.execute(
        """
        INSERT INTO track_identity (
            identity_key,
            ingested_at,
            ingestion_method,
            ingestion_source,
            ingestion_confidence
        ) VALUES (?, '2026-01-01T00:00:00Z', 'provider_api', 'test', 'high')
        """,
        (identity_key,),
    )
    row = conn.execute("SELECT id FROM track_identity WHERE identity_key = ?", (identity_key,)).fetchone()
    assert row is not None
    return int(row[0])


def test_library_track_sources_write_contract_and_json_validity() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    identity_id = _insert_identity(conn, "beatport:1")
    _ = identity_id

    write_library_track_source(
        conn,
        identity_key="beatport:1",
        provider="qobuz",
        provider_track_id="q1",
        source_url="https://example.invalid/qobuz/q1",
        raw_payload={"raw": True},
        metadata={"title": "T"},
    )

    row = conn.execute(
        """
        SELECT identity_key, provider, provider_track_id, source_url, raw_payload_json, metadata_json
        FROM library_track_sources
        WHERE identity_key = ? AND provider = ? AND provider_track_id = ?
        """,
        ("beatport:1", "qobuz", "q1"),
    ).fetchone()
    assert row is not None
    assert row["identity_key"] == "beatport:1"
    assert row["provider"] == "qobuz"
    assert row["provider_track_id"] == "q1"
    assert json.loads(row["raw_payload_json"]) == {"raw": True}
    assert json.loads(row["metadata_json"]) == {"title": "T"}


def test_qobuz_promotion_rejected_without_corroboration_before_db_update(caplog) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    identity_id = _insert_identity(conn, "beatport:2")

    statements: list[str] = []
    conn.set_trace_callback(statements.append)

    with pytest.raises(ValueError, match="corroboration"):
        maybe_promote_qobuz_id(
            conn,
            identity_id=identity_id,
            qobuz_id="q2",
            isrc="USRC17607839",
            corroborated_by=[],
        )

    assert not any("UPDATE track_identity" in stmt for stmt in statements)
    row = conn.execute("SELECT qobuz_id FROM track_identity WHERE id = ?", (identity_id,)).fetchone()
    assert row is not None
    assert row["qobuz_id"] is None


def test_duplicate_qobuz_id_raises_and_is_logged(caplog) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    id1 = _insert_identity(conn, "beatport:3")
    id2 = _insert_identity(conn, "beatport:4")

    maybe_promote_qobuz_id(
        conn,
        identity_id=id1,
        qobuz_id="q-dup",
        isrc="USRC17607839",
        corroborated_by=["beatport"],
    )

    caplog.set_level(logging.WARNING)
    with pytest.raises(sqlite3.IntegrityError):
        maybe_promote_qobuz_id(
            conn,
            identity_id=id2,
            qobuz_id="q-dup",
            isrc="USRC17607839",
            corroborated_by=["beatport"],
        )

    assert any("qobuz_id promotion failed" in rec.message for rec in caplog.records)


def test_db_uniqueness_is_last_line_of_defense_on_duplicate_qobuz_id() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)

    _insert_identity(conn, "beatport:5")
    _insert_identity(conn, "beatport:6")

    conn.execute("UPDATE track_identity SET qobuz_id = ? WHERE identity_key = ?", ("q-last", "beatport:5"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE track_identity SET qobuz_id = ? WHERE identity_key = ?", ("q-last", "beatport:6"))

