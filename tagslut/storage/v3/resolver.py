"""Evidence-ranked identity resolver for the existing v3 catalog."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from tagslut.storage.v3.schema import ensure_identity_resolution_artifacts

PROVIDER_COLUMNS: tuple[str, ...] = (
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "spotify_id",
    "apple_music_id",
    "deezer_id",
    "traxsource_id",
    "itunes_id",
    "musicbrainz_id",
)

TEXT_CANDIDATE_SCORE = 0.65
FUZZY_SCORE_THRESHOLD = 0.92
CHROMAPRINT_DURATION_TOLERANCE_S = 2.0


@dataclass(frozen=True)
class ResolverInput:
    asset_id: int | None = None
    path: str | None = None
    content_sha256: str | None = None
    streaminfo_md5: str | None = None
    chromaprint_fingerprint: str | None = None
    duration_s: float | None = None
    isrc: str | None = None
    provider_ids: dict[str, str] = field(default_factory=dict)
    artist: str | None = None
    title: str | None = None
    source_system: str = "resolver"
    source_ref: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolutionCandidate:
    identity_id: int
    match_method: str
    score: float
    confidence: str
    decision: str
    reason: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ResolutionResult:
    decision: str
    identity_id: int | None
    confidence: float
    run_id: int | None
    candidates: tuple[ResolutionCandidate, ...]
    reasons: dict[str, Any]
    evidence_ids: tuple[int, ...] = ()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _present_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.OperationalError:
        return set()


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text.lower()).strip()


def _norm_isrc(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return re.sub(r"[\s-]+", "", text.upper()) or None


def _active_where(conn: sqlite3.Connection, alias: str = "ti") -> str:
    if _column_exists(conn, "track_identity", "merged_into_id"):
        return f" AND {alias}.merged_into_id IS NULL"
    return ""


def _resolve_active_id(conn: sqlite3.Connection, identity_id: int) -> int:
    if not _column_exists(conn, "track_identity", "merged_into_id"):
        return identity_id
    seen: set[int] = set()
    current = identity_id
    while current not in seen:
        seen.add(current)
        row = conn.execute(
            "SELECT merged_into_id FROM track_identity WHERE id = ?",
            (current,),
        ).fetchone()
        if row is None or row[0] is None:
            return current
        current = int(row[0])
    return identity_id


def _identity_isrc(conn: sqlite3.Connection, identity_id: int) -> str | None:
    if not _column_exists(conn, "track_identity", "isrc"):
        return None
    row = conn.execute("SELECT isrc FROM track_identity WHERE id = ?", (identity_id,)).fetchone()
    if row is None:
        return None
    return _norm_isrc(row[0])


def _add_candidate(
    candidates: dict[tuple[int, str], ResolutionCandidate],
    *,
    identity_id: int,
    match_method: str,
    score: float,
    confidence: str,
    decision: str,
    reason: dict[str, Any],
    evidence_ids: list[int] | tuple[int, ...] = (),
) -> None:
    key = (identity_id, match_method)
    existing = candidates.get(key)
    item = ResolutionCandidate(
        identity_id=identity_id,
        match_method=match_method,
        score=score,
        confidence=confidence,
        decision=decision,
        reason=reason,
        evidence_ids=tuple(evidence_ids),
    )
    if existing is None or item.score > existing.score:
        candidates[key] = item


def _candidate_rows_for_identity_ids(
    conn: sqlite3.Connection,
    identity_ids: list[int],
) -> list[int]:
    return sorted({_resolve_active_id(conn, int(identity_id)) for identity_id in identity_ids})


def _lookup_identity_ids_by_field(
    conn: sqlite3.Connection,
    column: str,
    value: str,
    *,
    isrc: bool = False,
) -> list[int]:
    if not _table_exists(conn, "track_identity") or not _column_exists(conn, "track_identity", column):
        return []
    where = f"{column} = ?"
    param = value
    if isrc:
        where = "UPPER(REPLACE(REPLACE(isrc, '-', ''), ' ', '')) = ?"
        param = _norm_isrc(value) or value
    rows = conn.execute(
        f"""
        SELECT id
        FROM track_identity ti
        WHERE {where}
        {_active_where(conn)}
        ORDER BY id ASC
        """,
        (param,),
    ).fetchall()
    return _candidate_rows_for_identity_ids(conn, [int(row[0]) for row in rows])


def _lookup_identity_ids_by_asset_field(
    conn: sqlite3.Connection,
    column: str,
    value: str,
) -> list[int]:
    if not (
        _table_exists(conn, "asset_file")
        and _table_exists(conn, "asset_link")
        and _column_exists(conn, "asset_file", column)
    ):
        return []
    active_link = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    rows = conn.execute(
        f"""
        SELECT al.identity_id
        FROM asset_file af
        JOIN asset_link al ON al.asset_id = af.id
        WHERE af.{column} = ?
          {active_link}
        ORDER BY al.id ASC
        """,
        (value,),
    ).fetchall()
    return _candidate_rows_for_identity_ids(conn, [int(row[0]) for row in rows])


def _lookup_identity_ids_by_chromaprint(
    conn: sqlite3.Connection,
    fingerprint: str,
    duration_s: float | None,
) -> list[int]:
    if not (
        _table_exists(conn, "asset_file")
        and _table_exists(conn, "asset_link")
        and _column_exists(conn, "asset_file", "chromaprint_fingerprint")
    ):
        return []
    duration_col = "chromaprint_duration_s" if _column_exists(conn, "asset_file", "chromaprint_duration_s") else "duration_s"
    active_link = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
    rows = conn.execute(
        f"""
        SELECT al.identity_id, af.{duration_col}
        FROM asset_file af
        JOIN asset_link al ON al.asset_id = af.id
        WHERE af.chromaprint_fingerprint = ?
          {active_link}
        ORDER BY al.id ASC
        """,
        (fingerprint,),
    ).fetchall()
    matched: list[int] = []
    for row in rows:
        if duration_s is not None and row[1] is not None:
            try:
                if abs(float(duration_s) - float(row[1])) > CHROMAPRINT_DURATION_TOLERANCE_S:
                    continue
            except (TypeError, ValueError):
                pass
        matched.append(int(row[0]))
    return _candidate_rows_for_identity_ids(conn, matched)


def _lookup_identity_ids_by_path(conn: sqlite3.Connection, path: str) -> list[int]:
    matched: list[int] = []
    if _table_exists(conn, "mp3_asset") and _column_exists(conn, "mp3_asset", "path"):
        rows = conn.execute(
            "SELECT identity_id FROM mp3_asset WHERE path = ? AND identity_id IS NOT NULL",
            (path,),
        ).fetchall()
        matched.extend(int(row[0]) for row in rows)
    if _table_exists(conn, "asset_file") and _table_exists(conn, "asset_link"):
        active_link = "AND al.active = 1" if _column_exists(conn, "asset_link", "active") else ""
        rows = conn.execute(
            f"""
            SELECT al.identity_id
            FROM asset_file af
            JOIN asset_link al ON al.asset_id = af.id
            WHERE af.path = ?
              {active_link}
            """,
            (path,),
        ).fetchall()
        matched.extend(int(row[0]) for row in rows)
    return _candidate_rows_for_identity_ids(conn, matched)


def _lookup_text_candidates(
    conn: sqlite3.Connection,
    artist: str | None,
    title: str | None,
    *,
    fuzzy: bool,
) -> list[tuple[int, float]]:
    artist_norm = _norm_name(artist)
    title_norm = _norm_name(title)
    if not artist_norm or not title_norm or not _table_exists(conn, "track_identity"):
        return []
    columns = _present_columns(conn, "track_identity")
    if "artist_norm" not in columns or "title_norm" not in columns:
        return []
    if not fuzzy:
        rows = conn.execute(
            f"""
            SELECT id
            FROM track_identity ti
            WHERE lower(artist_norm) = ? AND lower(title_norm) = ?
            {_active_where(conn)}
            ORDER BY id ASC
            """,
            (artist_norm, title_norm),
        ).fetchall()
        return [(identity_id, TEXT_CANDIDATE_SCORE) for identity_id in _candidate_rows_for_identity_ids(conn, [int(row[0]) for row in rows])]

    rows = conn.execute(
        f"""
        SELECT id, artist_norm, title_norm
        FROM track_identity ti
        WHERE artist_norm IS NOT NULL AND title_norm IS NOT NULL
        {_active_where(conn)}
        ORDER BY id ASC
        """
    ).fetchall()
    query = f"{artist_norm} {title_norm}"
    matches: list[tuple[int, float]] = []
    for row in rows:
        candidate = f"{_norm_name(row[1]) or ''} {_norm_name(row[2]) or ''}".strip()
        if not candidate:
            continue
        score = SequenceMatcher(None, query, candidate).ratio()
        if score >= FUZZY_SCORE_THRESHOLD:
            matches.append((_resolve_active_id(conn, int(row[0])), round(score, 4)))
    deduped: dict[int, float] = {}
    for identity_id, score in matches:
        deduped[identity_id] = max(deduped.get(identity_id, 0.0), score)
    return sorted(deduped.items(), key=lambda item: (-item[1], item[0]))


def write_identity_evidence(
    conn: sqlite3.Connection,
    *,
    identity_id: int | None,
    asset_id: int | None = None,
    evidence_type: str,
    evidence_key: str,
    evidence_value: str | int | float | None,
    provider: str | None = None,
    source_system: str,
    source_ref: str | None = None,
    confidence: float | None = None,
    conflict_state: str = "unreviewed",
    payload: dict[str, Any] | None = None,
) -> int | None:
    value = _norm_text(evidence_value)
    if not value:
        return None
    ensure_identity_resolution_artifacts(conn)
    cursor = conn.execute(
        """
        INSERT INTO identity_evidence (
            identity_id, asset_id, evidence_type, evidence_key, evidence_value,
            provider, source_system, source_ref, confidence, conflict_state,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            identity_id,
            asset_id,
            evidence_type,
            evidence_key,
            value,
            provider,
            source_system,
            source_ref,
            confidence,
            conflict_state,
            _json(payload or {}),
        ),
    )
    return int(cursor.lastrowid)


def record_duplicate_cohort(
    conn: sqlite3.Connection,
    *,
    cohort_type: str,
    cohort_key: str,
    identity_ids: list[int],
    reason: dict[str, Any],
) -> int:
    ensure_identity_resolution_artifacts(conn)
    conn.execute(
        """
        INSERT INTO identity_duplicate_cohort (cohort_key, cohort_type, reason_json)
        VALUES (?, ?, ?)
        ON CONFLICT(cohort_key) DO UPDATE SET
            reason_json = excluded.reason_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (cohort_key, cohort_type, _json(reason)),
    )
    row = conn.execute(
        "SELECT id FROM identity_duplicate_cohort WHERE cohort_key = ?",
        (cohort_key,),
    ).fetchone()
    cohort_id = int(row[0])
    for identity_id in sorted(set(identity_ids)):
        conn.execute(
            """
            INSERT OR IGNORE INTO identity_duplicate_cohort_member (
                cohort_id, identity_id, role, reason_json
            )
            VALUES (?, ?, 'candidate', ?)
            """,
            (cohort_id, identity_id, _json(reason)),
        )
    return cohort_id


def _persist_run(
    conn: sqlite3.Connection,
    resolver_input: ResolverInput,
    result: ResolutionResult,
) -> int:
    run_key = (
        f"{resolver_input.source_system}:"
        f"{resolver_input.source_ref or 'input'}:"
        f"{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%S%f')}:"
        f"{uuid.uuid4().hex[:8]}"
    )
    cursor = conn.execute(
        """
        INSERT INTO identity_resolution_run (
            run_key, source_system, source_ref, input_json, decision,
            accepted_identity_id, confidence, reason_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_key,
            resolver_input.source_system,
            resolver_input.source_ref,
            _json(_resolver_input_json(resolver_input)),
            result.decision,
            result.identity_id,
            result.confidence,
            _json(result.reasons),
        ),
    )
    run_id = int(cursor.lastrowid)
    for rank, candidate in enumerate(result.candidates, 1):
        conn.execute(
            """
            INSERT OR IGNORE INTO identity_resolution_candidate (
                run_id, identity_id, rank, score, match_method, confidence,
                decision, evidence_ids_json, reason_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                candidate.identity_id,
                rank,
                candidate.score,
                candidate.match_method,
                candidate.confidence,
                candidate.decision,
                _json(list(candidate.evidence_ids)),
                _json(candidate.reason),
            ),
        )
    return run_id


def _resolver_input_json(resolver_input: ResolverInput) -> dict[str, Any]:
    return {
        "asset_id": resolver_input.asset_id,
        "path": resolver_input.path,
        "content_sha256": resolver_input.content_sha256,
        "streaminfo_md5": resolver_input.streaminfo_md5,
        "chromaprint_fingerprint": resolver_input.chromaprint_fingerprint,
        "duration_s": resolver_input.duration_s,
        "isrc": resolver_input.isrc,
        "provider_ids": resolver_input.provider_ids,
        "artist": resolver_input.artist,
        "title": resolver_input.title,
        "payload": resolver_input.payload,
    }


def _finalize_result(
    conn: sqlite3.Connection,
    resolver_input: ResolverInput,
    *,
    decision: str,
    identity_id: int | None,
    confidence: float,
    candidates: dict[tuple[int, str], ResolutionCandidate],
    reasons: dict[str, Any],
    evidence_ids: list[int],
    persist: bool,
) -> ResolutionResult:
    ordered = tuple(
        sorted(
            candidates.values(),
            key=lambda candidate: (-candidate.score, candidate.identity_id, candidate.match_method),
        )
    )
    result = ResolutionResult(
        decision=decision,
        identity_id=identity_id,
        confidence=confidence,
        run_id=None,
        candidates=ordered,
        reasons=reasons,
        evidence_ids=tuple(evidence_ids),
    )
    if persist:
        ensure_identity_resolution_artifacts(conn)
        run_id = _persist_run(conn, resolver_input, result)
        result = ResolutionResult(
            decision=result.decision,
            identity_id=result.identity_id,
            confidence=result.confidence,
            run_id=run_id,
            candidates=result.candidates,
            reasons=result.reasons,
            evidence_ids=result.evidence_ids,
        )
    return result


def _accept_if_unique(
    conn: sqlite3.Connection,
    resolver_input: ResolverInput,
    *,
    method: str,
    identity_ids: list[int],
    score: float,
    confidence: str,
    reason: dict[str, Any],
    evidence_type: str,
    evidence_key: str,
    evidence_value: str | None,
    provider: str | None = None,
    persist: bool,
) -> ResolutionResult | None:
    candidates: dict[tuple[int, str], ResolutionCandidate] = {}
    evidence_ids: list[int] = []
    ids = sorted(set(identity_ids))
    if not ids:
        return None
    if len(ids) == 1:
        evidence_id = None
        if persist:
            evidence_id = write_identity_evidence(
                conn,
                identity_id=ids[0],
                asset_id=resolver_input.asset_id,
                evidence_type=evidence_type,
                evidence_key=evidence_key,
                evidence_value=evidence_value,
                provider=provider,
                source_system=resolver_input.source_system,
                source_ref=resolver_input.source_ref,
                confidence=score,
                conflict_state="accepted",
                payload=reason,
            )
            if evidence_id is not None:
                evidence_ids.append(evidence_id)
        _add_candidate(
            candidates,
            identity_id=ids[0],
            match_method=method,
            score=score,
            confidence=confidence,
            decision="accepted",
            reason=reason,
            evidence_ids=evidence_ids,
        )
        return _finalize_result(
            conn,
            resolver_input,
            decision="accepted",
            identity_id=ids[0],
            confidence=score,
            candidates=candidates,
            reasons={"accepted_by": method, **reason},
            evidence_ids=evidence_ids,
            persist=persist,
        )

    if persist:
        cohort_type = {
            "provider_id": "provider_conflict",
            "isrc": "isrc_collision",
            "chromaprint": "fingerprint_collision",
        }.get(evidence_type, "text_ambiguity")
        record_duplicate_cohort(
            conn,
            cohort_type=cohort_type,
            cohort_key=f"{cohort_type}:{evidence_key}:{evidence_value}",
            identity_ids=ids,
            reason={**reason, "method": method, "identity_ids": ids},
        )
    for identity_id in ids:
        evidence_id = None
        if persist:
            evidence_id = write_identity_evidence(
                conn,
                identity_id=identity_id,
                asset_id=resolver_input.asset_id,
                evidence_type=evidence_type,
                evidence_key=evidence_key,
                evidence_value=evidence_value,
                provider=provider,
                source_system=resolver_input.source_system,
                source_ref=resolver_input.source_ref,
                confidence=score,
                conflict_state="conflict",
                payload=reason,
            )
            if evidence_id is not None:
                evidence_ids.append(evidence_id)
        _add_candidate(
            candidates,
            identity_id=identity_id,
            match_method=method,
            score=score,
            confidence=confidence,
            decision="ambiguous",
            reason=reason,
            evidence_ids=[evidence_id] if evidence_id is not None else [],
        )
    return _finalize_result(
        conn,
        resolver_input,
        decision="ambiguous",
        identity_id=None,
        confidence=score,
        candidates=candidates,
        reasons={"ambiguous_by": method, **reason, "identity_ids": ids},
        evidence_ids=evidence_ids,
        persist=persist,
    )


def resolve_identity(
    conn: sqlite3.Connection,
    resolver_input: ResolverInput,
    *,
    persist: bool = True,
    allow_text_auto_match: bool = False,
) -> ResolutionResult:
    """Resolve against v3 identities using ranked evidence.

    Exact/fuzzy text matches are stored as review candidates by default and do
    not return an accepted identity unless allow_text_auto_match=True.
    """
    if persist:
        ensure_identity_resolution_artifacts(conn)

    if resolver_input.asset_id is not None and _table_exists(conn, "asset_link"):
        active = "AND active = 1" if _column_exists(conn, "asset_link", "active") else ""
        rows = conn.execute(
            f"""
            SELECT identity_id
            FROM asset_link
            WHERE asset_id = ?
            {active}
            ORDER BY id ASC
            """,
            (resolver_input.asset_id,),
        ).fetchall()
        result = _accept_if_unique(
            conn,
            resolver_input,
            method="asset_link",
            identity_ids=_candidate_rows_for_identity_ids(conn, [int(row[0]) for row in rows]),
            score=1.0,
            confidence="verified",
            reason={"asset_id": resolver_input.asset_id},
            evidence_type="asset_link",
            evidence_key="asset_id",
            evidence_value=str(resolver_input.asset_id),
            persist=persist,
        )
        if result is not None:
            return result

    for field_name, method, score in (
        ("content_sha256", "content_sha256", 0.99),
        ("streaminfo_md5", "streaminfo_md5", 0.98),
    ):
        value = _norm_text(getattr(resolver_input, field_name))
        if not value:
            continue
        result = _accept_if_unique(
            conn,
            resolver_input,
            method=method,
            identity_ids=_lookup_identity_ids_by_asset_field(conn, field_name, value),
            score=score,
            confidence="verified",
            reason={field_name: value},
            evidence_type=method,
            evidence_key=field_name,
            evidence_value=value,
            persist=persist,
        )
        if result is not None:
            return result

    provider_candidates: dict[int, dict[str, Any]] = {}
    input_isrc = _norm_isrc(resolver_input.isrc)
    for provider, raw_value in resolver_input.provider_ids.items():
        provider_column = provider if provider.endswith("_id") else f"{provider}_id"
        if provider_column not in PROVIDER_COLUMNS:
            continue
        value = _norm_text(raw_value)
        if not value:
            continue
        ids = _lookup_identity_ids_by_field(conn, provider_column, value)
        for identity_id in ids:
            candidate_isrc = _identity_isrc(conn, identity_id)
            conflicts_isrc = bool(input_isrc and candidate_isrc and input_isrc != candidate_isrc)
            provider_candidates[identity_id] = {
                "provider": provider_column.removesuffix("_id"),
                "provider_column": provider_column,
                "provider_id": value,
                "conflicts_isrc": conflicts_isrc,
                "candidate_isrc": candidate_isrc,
            }

    non_conflicting_provider_ids = [
        identity_id
        for identity_id, info in provider_candidates.items()
        if not info["conflicts_isrc"]
    ]
    if provider_candidates:
        if len(set(non_conflicting_provider_ids)) == 1:
            identity_id = non_conflicting_provider_ids[0]
            info = provider_candidates[identity_id]
            result = _accept_if_unique(
                conn,
                resolver_input,
                method="provider_id",
                identity_ids=[identity_id],
                score=0.94,
                confidence="high",
                reason=info,
                evidence_type="provider_id",
                evidence_key=str(info["provider_column"]),
                evidence_value=str(info["provider_id"]),
                provider=str(info["provider"]),
                persist=persist,
            )
            if result is not None:
                return result
        else:
            ids = sorted(provider_candidates)
            if persist:
                record_duplicate_cohort(
                    conn,
                    cohort_type="provider_conflict",
                    cohort_key=f"provider_conflict:{resolver_input.source_system}:{resolver_input.source_ref or uuid.uuid4().hex}",
                    identity_ids=ids,
                    reason={"provider_candidates": provider_candidates, "input_isrc": input_isrc},
                )
            candidates: dict[tuple[int, str], ResolutionCandidate] = {}
            evidence_ids: list[int] = []
            for identity_id, info in provider_candidates.items():
                evidence_id = write_identity_evidence(
                    conn,
                    identity_id=identity_id,
                    asset_id=resolver_input.asset_id,
                    evidence_type="provider_id",
                    evidence_key=str(info["provider_column"]),
                    evidence_value=str(info["provider_id"]),
                    provider=str(info["provider"]),
                    source_system=resolver_input.source_system,
                    source_ref=resolver_input.source_ref,
                    confidence=0.94,
                    conflict_state="conflict" if info["conflicts_isrc"] else "unreviewed",
                    payload={"input_isrc": input_isrc, **info},
                ) if persist else None
                if evidence_id is not None:
                    evidence_ids.append(evidence_id)
                _add_candidate(
                    candidates,
                    identity_id=identity_id,
                    match_method="provider_id",
                    score=0.94,
                    confidence="high",
                    decision="ambiguous",
                    reason={"input_isrc": input_isrc, **info},
                    evidence_ids=[evidence_id] if evidence_id is not None else [],
                )
            return _finalize_result(
                conn,
                resolver_input,
                decision="ambiguous",
                identity_id=None,
                confidence=0.94,
                candidates=candidates,
                reasons={"ambiguous_by": "provider_id", "input_isrc": input_isrc},
                evidence_ids=evidence_ids,
                persist=persist,
            )

    fingerprint = _norm_text(resolver_input.chromaprint_fingerprint)
    if fingerprint:
        result = _accept_if_unique(
            conn,
            resolver_input,
            method="chromaprint",
            identity_ids=_lookup_identity_ids_by_chromaprint(
                conn,
                fingerprint,
                resolver_input.duration_s,
            ),
            score=0.93,
            confidence="verified",
            reason={
                "chromaprint_fingerprint": fingerprint,
                "duration_s": resolver_input.duration_s,
            },
            evidence_type="chromaprint",
            evidence_key="chromaprint_fingerprint",
            evidence_value=fingerprint,
            persist=persist,
        )
        if result is not None:
            return result

    if input_isrc:
        result = _accept_if_unique(
            conn,
            resolver_input,
            method="isrc",
            identity_ids=_lookup_identity_ids_by_field(conn, "isrc", input_isrc, isrc=True),
            score=0.9,
            confidence="high",
            reason={"isrc": input_isrc},
            evidence_type="isrc",
            evidence_key="isrc",
            evidence_value=input_isrc,
            persist=persist,
        )
        if result is not None:
            return result

    if resolver_input.path:
        result = _accept_if_unique(
            conn,
            resolver_input,
            method="lexicon_path",
            identity_ids=_lookup_identity_ids_by_path(conn, resolver_input.path),
            score=0.86,
            confidence="high",
            reason={"path": resolver_input.path},
            evidence_type="lexicon_path",
            evidence_key="path",
            evidence_value=resolver_input.path,
            persist=persist,
        )
        if result is not None:
            return result

    candidates: dict[tuple[int, str], ResolutionCandidate] = {}
    evidence_ids: list[int] = []
    exact_text = _lookup_text_candidates(
        conn,
        resolver_input.artist,
        resolver_input.title,
        fuzzy=False,
    )
    for identity_id, score in exact_text:
        decision = "accepted" if allow_text_auto_match and len(exact_text) == 1 else "candidate"
        evidence_id = None
        if persist:
            evidence_id = write_identity_evidence(
                conn,
                identity_id=identity_id,
                asset_id=resolver_input.asset_id,
                evidence_type="text",
                evidence_key="artist_title",
                evidence_value=f"{_norm_name(resolver_input.artist)}|{_norm_name(resolver_input.title)}",
                source_system=resolver_input.source_system,
                source_ref=resolver_input.source_ref,
                confidence=score,
                conflict_state="accepted" if decision == "accepted" else "unreviewed",
                payload={"artist": resolver_input.artist, "title": resolver_input.title},
            )
            if evidence_id is not None:
                evidence_ids.append(evidence_id)
        _add_candidate(
            candidates,
            identity_id=identity_id,
            match_method="exact_text",
            score=score,
            confidence="medium",
            decision=decision,
            reason={"artist": resolver_input.artist, "title": resolver_input.title},
            evidence_ids=[evidence_id] if evidence_id is not None else [],
        )

    fuzzy_text = _lookup_text_candidates(
        conn,
        resolver_input.artist,
        resolver_input.title,
        fuzzy=True,
    )
    for identity_id, score in fuzzy_text:
        if any(candidate.identity_id == identity_id for candidate in candidates.values()):
            continue
        evidence_id = None
        if persist:
            evidence_id = write_identity_evidence(
                conn,
                identity_id=identity_id,
                asset_id=resolver_input.asset_id,
                evidence_type="text",
                evidence_key="fuzzy_artist_title",
                evidence_value=f"{_norm_name(resolver_input.artist)}|{_norm_name(resolver_input.title)}",
                source_system=resolver_input.source_system,
                source_ref=resolver_input.source_ref,
                confidence=score,
                conflict_state="unreviewed",
                payload={"artist": resolver_input.artist, "title": resolver_input.title, "score": score},
            )
            if evidence_id is not None:
                evidence_ids.append(evidence_id)
        _add_candidate(
            candidates,
            identity_id=identity_id,
            match_method="fuzzy_text",
            score=score,
            confidence="low",
            decision="candidate",
            reason={"artist": resolver_input.artist, "title": resolver_input.title, "score": score},
            evidence_ids=[evidence_id] if evidence_id is not None else [],
        )

    if allow_text_auto_match and len(exact_text) == 1:
        identity_id = exact_text[0][0]
        return _finalize_result(
            conn,
            resolver_input,
            decision="accepted",
            identity_id=identity_id,
            confidence=TEXT_CANDIDATE_SCORE,
            candidates=candidates,
            reasons={"accepted_by": "exact_text", "text_auto_match": True},
            evidence_ids=evidence_ids,
            persist=persist,
        )

    if candidates:
        ids = sorted({candidate.identity_id for candidate in candidates.values()})
        decision = "ambiguous" if len(ids) > 1 else "candidate_only"
        if persist and len(ids) > 1:
            record_duplicate_cohort(
                conn,
                cohort_type="text_ambiguity",
                cohort_key=(
                    "text_ambiguity:"
                    f"{_norm_name(resolver_input.artist)}:"
                    f"{_norm_name(resolver_input.title)}:"
                    f"{resolver_input.source_system}:"
                    f"{resolver_input.source_ref or uuid.uuid4().hex}"
                ),
                identity_ids=ids,
                reason={"artist": resolver_input.artist, "title": resolver_input.title},
            )
        return _finalize_result(
            conn,
            resolver_input,
            decision=decision,
            identity_id=None,
            confidence=max(candidate.score for candidate in candidates.values()),
            candidates=candidates,
            reasons={
                "review_required": True,
                "text_auto_match": allow_text_auto_match,
                "candidate_identity_ids": ids,
            },
            evidence_ids=evidence_ids,
            persist=persist,
        )

    return _finalize_result(
        conn,
        resolver_input,
        decision="unresolved",
        identity_id=None,
        confidence=0.0,
        candidates={},
        reasons={"matched": False},
        evidence_ids=[],
        persist=persist,
    )
