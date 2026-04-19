from __future__ import annotations

import sqlite3

from tagslut.storage.v3.resolver import ResolverInput, resolve_identity
from tagslut.storage.v3.schema import create_schema_v3


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    create_schema_v3(conn)
    return conn


def _insert_identity(
    conn: sqlite3.Connection,
    *,
    identity_key: str,
    isrc: str | None = None,
    beatport_id: str | None = None,
    artist_norm: str | None = None,
    title_norm: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO track_identity (
            identity_key, isrc, beatport_id, artist_norm, title_norm,
            ingested_at, ingestion_method, ingestion_source, ingestion_confidence
        )
        VALUES (?, ?, ?, ?, ?, '2026-01-01T00:00:00+00:00', 'migration', 'test', 'legacy')
        """,
        (identity_key, isrc, beatport_id, artist_norm, title_norm),
    )
    return int(cur.lastrowid)


def test_resolver_accepts_unique_isrc_and_persists_run() -> None:
    conn = _conn()
    try:
        identity_id = _insert_identity(conn, identity_key="isrc:abc", isrc="ABC")

        result = resolve_identity(
            conn,
            ResolverInput(isrc="abc", source_system="test", source_ref="isrc"),
        )

        assert result.decision == "accepted"
        assert result.identity_id == identity_id
        assert conn.execute("SELECT COUNT(*) FROM identity_resolution_run").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM identity_evidence").fetchone()[0] == 1
    finally:
        conn.close()


def test_resolver_keeps_exact_text_candidate_review_only() -> None:
    conn = _conn()
    try:
        identity_id = _insert_identity(
            conn,
            identity_key="text:artist|track",
            artist_norm="artist",
            title_norm="track",
        )

        result = resolve_identity(
            conn,
            ResolverInput(
                artist="Artist",
                title="Track",
                source_system="test",
                source_ref="text",
            ),
        )

        assert result.decision == "candidate_only"
        assert result.identity_id is None
        assert [candidate.identity_id for candidate in result.candidates] == [identity_id]
        candidate_row = conn.execute(
            "SELECT decision, match_method FROM identity_resolution_candidate"
        ).fetchone()
        assert candidate_row == ("candidate", "exact_text")
    finally:
        conn.close()


def test_resolver_records_provider_isrc_conflict_as_ambiguous() -> None:
    conn = _conn()
    try:
        first_id = _insert_identity(
            conn,
            identity_key="isrc:one",
            isrc="ONE",
            beatport_id="BP1",
        )
        second_id = _insert_identity(
            conn,
            identity_key="isrc:two",
            isrc="TWO",
            beatport_id="BP2",
        )

        result = resolve_identity(
            conn,
            ResolverInput(
                isrc="ONE",
                provider_ids={"beatport_id": "BP2"},
                source_system="test",
                source_ref="conflict",
            ),
        )

        assert result.decision == "ambiguous"
        assert sorted(candidate.identity_id for candidate in result.candidates) == [second_id]
        assert conn.execute("SELECT cohort_type FROM identity_duplicate_cohort").fetchone()[0] == "provider_conflict"
        assert first_id != second_id
    finally:
        conn.close()
