"""Backfill track_identity.spotify_id by exact Spotify ISRC lookup."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tagslut.intake.spotify import SpotifyIntakeError, SpotifyMetadataClient, SpotifyTrack
from tagslut.storage.v3.identity_service import merge_identity_fields_if_empty


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return " ".join(text.lower().split())


def _norm_title_key(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    text = re.sub(r"[^0-9a-z]+", " ", text.lower())
    text = " ".join(text.split())
    return text or None


def _artist_parts(value: Any) -> tuple[str, ...]:
    text = _norm_name(value)
    if not text:
        return ()
    parts = re.split(r"\s*(?:,|&| feat\.? | ft\.? | featuring | x )\s*", text)
    normalized = sorted({part.strip() for part in parts if part.strip()})
    return tuple(normalized)


def _artist_sets_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return False
    left_set = set(left)
    right_set = set(right)
    return left_set == right_set or left_set.issubset(right_set) or right_set.issubset(left_set)


def _norm_isrc(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return text.upper()


@dataclass(frozen=True)
class CandidateDetail:
    spotify_id: str
    artist: str
    title: str
    album: str
    release_date: str
    duration_ms: int | None
    artist_score: int
    title_score: int
    duration_score: int

    @property
    def score(self) -> int:
        return self.artist_score + self.title_score + self.duration_score


@dataclass(frozen=True)
class CandidateSelection:
    spotify_id: str | None
    reason: str
    details: tuple[CandidateDetail, ...] = ()


@dataclass
class InterruptState:
    requested: bool = False
    signal_name: str | None = None


def _row_artist_name(row: sqlite3.Row | dict[str, Any]) -> str | None:
    return _norm_text(row["canonical_artist"]) or _norm_text(row["artist_norm"])


def _row_title_name(row: sqlite3.Row | dict[str, Any]) -> str | None:
    return _norm_text(row["canonical_title"]) or _norm_text(row["title_norm"])


def _candidate_detail(
    hit: SpotifyTrack,
    *,
    row_artists: tuple[str, ...],
    row_title_key: str | None,
    row_duration_ms: int | None,
) -> CandidateDetail:
    hit_artists = _artist_parts(hit.artist)
    hit_title_key = _norm_title_key(hit.title)
    artist_score = 1 if _artist_sets_compatible(hit_artists, row_artists) else 0
    title_score = 1 if row_title_key and hit_title_key == row_title_key else 0
    duration_score = 1 if row_duration_ms and hit.duration_ms == row_duration_ms else 0
    return CandidateDetail(
        spotify_id=str(hit.spotify_id),
        artist=str(hit.artist),
        title=str(hit.title),
        album=str(hit.album),
        release_date=str(hit.release_date),
        duration_ms=hit.duration_ms,
        artist_score=artist_score,
        title_score=title_score,
        duration_score=duration_score,
    )


def _row_duration_ms(row: sqlite3.Row | dict[str, Any]) -> int | None:
    raw = row["duration_ref_ms"]
    if raw in (None, ""):
        return None
    return int(raw)


def _row_display_name(row: sqlite3.Row | dict[str, Any]) -> str:
    artist = _row_artist_name(row) or "?"
    title = _row_title_name(row) or "?"
    return f"{artist} - {title}"


def _format_duration_ms(value: int | None) -> str:
    if value is None:
        return "?"
    return f"{value} ms"


def _format_candidate_brief(detail: CandidateDetail) -> str:
    return (
        f"{detail.spotify_id} | {detail.artist} - {detail.title} | "
        f"{detail.album or '?'} | {detail.release_date or '?'} | "
        f"{_format_duration_ms(detail.duration_ms)} | score {detail.score}/3"
    )


def _semantic_key(hit: SpotifyTrack) -> tuple[tuple[str, ...], str | None, int | None]:
    return (_artist_parts(hit.artist), _norm_title_key(hit.title), hit.duration_ms)


def _semantic_tie_break_key(hit: SpotifyTrack) -> tuple[str, int, str, str]:
    release_date = _norm_text(hit.release_date) or "9999-99-99"
    album = _norm_text(hit.album) or ""
    return (release_date, len(album), album.lower(), hit.spotify_id)


def choose_spotify_candidate(row: sqlite3.Row | dict[str, Any], hits: list[SpotifyTrack]) -> CandidateSelection:
    target_isrc = _norm_isrc(row["isrc"])
    if not target_isrc:
        return CandidateSelection(None, "missing_isrc")

    exact_hits = [hit for hit in hits if _norm_isrc(hit.isrc) == target_isrc and _norm_text(hit.spotify_id)]
    by_id: dict[str, SpotifyTrack] = {}
    for hit in exact_hits:
        by_id[str(hit.spotify_id)] = hit
    unique_hits = list(by_id.values())
    if not unique_hits:
        return CandidateSelection(None, "unresolved")
    if len(unique_hits) == 1:
        return CandidateSelection(
            str(unique_hits[0].spotify_id),
            "exact_isrc",
            (
                _candidate_detail(
                    unique_hits[0],
                    row_artists=_artist_parts(_row_artist_name(row)),
                    row_title_key=_norm_title_key(_row_title_name(row)),
                    row_duration_ms=_row_duration_ms(row),
                ),
            ),
        )

    row_artists = _artist_parts(row["artist_norm"] if row["artist_norm"] else row["canonical_artist"])
    row_title_key = _norm_title_key(row["title_norm"] if row["title_norm"] else row["canonical_title"])
    row_duration_ms = _row_duration_ms(row)

    scored: list[tuple[int, SpotifyTrack]] = []
    for hit in unique_hits:
        score = 0
        if _artist_sets_compatible(_artist_parts(hit.artist), row_artists):
            score += 1
        if row_title_key and _norm_title_key(hit.title) == row_title_key:
            score += 1
        if row_duration_ms and hit.duration_ms == row_duration_ms:
            score += 1
        scored.append((score, hit))
    scored.sort(key=lambda item: (-item[0], item[1].spotify_id))
    details = tuple(
        _candidate_detail(hit, row_artists=row_artists, row_title_key=row_title_key, row_duration_ms=row_duration_ms)
        for _, hit in scored
    )
    best_score = scored[0][0]
    if best_score < 2:
        return CandidateSelection(None, "ambiguous", details)
    top_hits = [hit for score, hit in scored if score == best_score]
    if len(top_hits) > 1:
        semantic_keys = {_semantic_key(hit) for hit in top_hits}
        if len(semantic_keys) == 1:
            chosen = min(top_hits, key=_semantic_tie_break_key)
            return CandidateSelection(str(chosen.spotify_id), "semantic_tie_break", details)
        return CandidateSelection(None, "ambiguous", details)
    return CandidateSelection(str(scored[0][1].spotify_id), "artist_title_tiebreak", details)


def _format_verbose_lines(
    row: sqlite3.Row,
    selection: CandidateSelection,
) -> list[str]:
    lines = [f"  DB: {_row_display_name(row)} [{_format_duration_ms(_row_duration_ms(row))}]"]
    if selection.reason == "semantic_tie_break":
        lines.append("  Decision: picked earliest release among equivalent Spotify matches")
    elif selection.reason == "artist_title_tiebreak":
        lines.append("  Decision: picked the only candidate with matching artist/title")
    chosen_ids = {selection.spotify_id} if selection.spotify_id else set()
    for detail in selection.details:
        prefix = "  Picked:" if detail.spotify_id in chosen_ids else "  Other: "
        lines.append(f"{prefix} {_format_candidate_brief(detail)}")
    return lines


def _install_interrupt_handler(state: InterruptState) -> dict[int, Any]:
    previous: dict[int, Any] = {}

    def _handler(signum: int, _frame: Any) -> None:
        state.requested = True
        state.signal_name = signal.Signals(signum).name
        print(
            f"interrupt {state.signal_name} received; stopping after current row",
            file=sys.stderr,
            flush=True,
        )

    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.getsignal(sig)
        signal.signal(sig, _handler)
    return previous


def _restore_interrupt_handler(previous: dict[int, Any]) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _normalized_terms(values: tuple[str, ...] | list[str] | None, *, upper: bool = False) -> tuple[str, ...]:
    if not values:
        return ()
    normalized: list[str] = []
    for value in values:
        text = _norm_text(value)
        if not text:
            continue
        normalized.append(text.upper() if upper else text.lower())
    return tuple(normalized)


def _select_rows(
    conn: sqlite3.Connection,
    *,
    resume_from_id: int,
    limit: int | None,
    newest_first: bool = True,
    artist_terms: tuple[str, ...] = (),
    title_terms: tuple[str, ...] = (),
    isrc_terms: tuple[str, ...] = (),
) -> list[sqlite3.Row]:
    merged_where = "AND merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    order_by = "id DESC" if newest_first else "id ASC"
    sql = f"""
        SELECT id, isrc, spotify_id, artist_norm, title_norm, canonical_artist, canonical_title
             , duration_ref_ms
        FROM track_identity
        WHERE 1=1
          {merged_where}
          AND isrc IS NOT NULL
          AND TRIM(isrc) != ''
          AND (spotify_id IS NULL OR TRIM(spotify_id) = '')
    """
    params: list[Any] = []
    if resume_from_id > 0:
        sql += " AND id < ?" if newest_first else " AND id > ?"
        params.append(resume_from_id)
    if isrc_terms:
        placeholders = ", ".join("?" for _ in isrc_terms)
        sql += f" AND UPPER(isrc) IN ({placeholders})"
        params.extend(isrc_terms)
    if artist_terms:
        artist_predicates = []
        for _ in artist_terms:
            artist_predicates.append(
                "(LOWER(COALESCE(canonical_artist, '')) LIKE ? OR LOWER(COALESCE(artist_norm, '')) LIKE ?)"
            )
        sql += " AND (" + " OR ".join(artist_predicates) + ")"
        for term in artist_terms:
            like = f"%{term}%"
            params.extend([like, like])
    if title_terms:
        title_predicates = []
        for _ in title_terms:
            title_predicates.append(
                "(LOWER(COALESCE(canonical_title, '')) LIKE ? OR LOWER(COALESCE(title_norm, '')) LIKE ?)"
            )
        sql += " AND (" + " OR ".join(title_predicates) + ")"
        for term in title_terms:
            like = f"%{term}%"
            params.extend([like, like])
    sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return conn.execute(sql, tuple(params)).fetchall()


def _spotify_id_conflicts(conn: sqlite3.Connection, identity_id: int, spotify_id: str) -> bool:
    merged_where = "AND merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    row = conn.execute(
        f"""
        SELECT id
        FROM track_identity
        WHERE spotify_id = ?
          AND id != ?
          {merged_where}
        LIMIT 1
        """,
        (spotify_id, int(identity_id)),
    ).fetchone()
    return row is not None


def run(
    *,
    db_path: Path,
    execute: bool,
    resume_from_id: int,
    limit: int | None,
    newest_first: bool = True,
    artist_terms: tuple[str, ...] = (),
    title_terms: tuple[str, ...] = (),
    isrc_terms: tuple[str, ...] = (),
    search_limit: int,
    commit_every: int,
    busy_timeout_ms: int,
    verbose: bool,
) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    interrupt_state = InterruptState()
    previous_handlers = _install_interrupt_handler(interrupt_state)
    try:
        rows = _select_rows(
            conn,
            resume_from_id=resume_from_id,
            limit=limit,
            newest_first=newest_first,
            artist_terms=artist_terms,
            title_terms=title_terms,
            isrc_terms=isrc_terms,
        )
        stats: dict[str, Any] = {
            "mode": "execute" if execute else "dry_run",
            "db_path": str(db_path),
            "processed": 0,
            "updated": 0,
            "unresolved": 0,
            "ambiguous": 0,
            "conflicts": 0,
            "errors": 0,
            "last_identity_id": 0,
            "resume_from_id": resume_from_id,
            "next_resume_from_id": resume_from_id,
            "order": "newest_first" if newest_first else "oldest_first",
            "interrupted": False,
            "interrupted_signal": None,
            "stopped_at": None,
            "filters": {
                "artist": list(artist_terms),
                "title": list(title_terms),
                "isrc": list(isrc_terms),
            },
        }

        if execute:
            conn.execute("BEGIN IMMEDIATE")

        with SpotifyMetadataClient() as spotify:
            for row in rows:
                if interrupt_state.requested:
                    break
                identity_id = int(row["id"])
                stats["processed"] += 1
                stats["last_identity_id"] = identity_id
                stats["next_resume_from_id"] = identity_id
                isrc = _norm_isrc(row["isrc"])
                if not isrc:
                    stats["unresolved"] += 1
                    continue
                try:
                    hits = spotify.search_by_isrc(isrc, limit=search_limit)
                    selection = choose_spotify_candidate(row, hits)
                    if selection.spotify_id is None:
                        stats[selection.reason] = int(stats.get(selection.reason, 0)) + 1
                        if verbose:
                            print(f"[skip] #{identity_id} {isrc} {selection.reason}", file=sys.stderr)
                            for line in _format_verbose_lines(row, selection):
                                print(line, file=sys.stderr)
                        continue
                    spotify_id = selection.spotify_id
                    if _spotify_id_conflicts(conn, identity_id, spotify_id):
                        stats["conflicts"] += 1
                        if verbose:
                            print(f"[skip] #{identity_id} {isrc} conflict on {spotify_id}", file=sys.stderr)
                        continue
                    if execute:
                        merge_identity_fields_if_empty(
                            conn,
                            identity_id,
                            {
                                "isrc": isrc,
                                "spotify_id": spotify_id,
                            },
                            {
                                "ingestion_method": "isrc_lookup",
                                "ingestion_source": f"spotify_api:isrc={isrc}",
                                "ingestion_confidence": "high",
                            },
                        )
                        if stats["updated"] > 0 and stats["updated"] % int(commit_every) == 0:
                            conn.commit()
                            conn.execute("BEGIN IMMEDIATE")
                    stats["updated"] += 1
                    if verbose:
                        print(f"[match] #{identity_id} {isrc} -> {spotify_id} ({selection.reason})", file=sys.stderr)
                        for line in _format_verbose_lines(row, selection):
                            print(line, file=sys.stderr)
                except SpotifyIntakeError as exc:
                    stats["errors"] += 1
                    if verbose:
                        print(f"[error] #{identity_id} {isrc} {exc}", file=sys.stderr)
                    if "rate_limited" in str(exc):
                        break
                except Exception:
                    stats["errors"] += 1
                    if verbose:
                        traceback.print_exc()

        if execute:
            conn.commit()
        stats["interrupted"] = interrupt_state.requested
        stats["interrupted_signal"] = interrupt_state.signal_name
        stats["stopped_at"] = datetime.now(timezone.utc).isoformat()
        return stats
    finally:
        _restore_interrupt_handler(previous_handlers)
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill track_identity.spotify_id by exact Spotify ISRC lookup.",
    )
    parser.add_argument("--db", type=Path, default=None, help="Path to SQLite DB (defaults to TAGSLUT_DB)")
    parser.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument(
        "--resume-from-id",
        type=int,
        default=0,
        help="Resume cursor. Default order is newest-first, so resume continues with lower ids.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N eligible identities")
    parser.add_argument("--artist", action="append", default=[], help="Only process rows whose artist contains this text (repeatable)")
    parser.add_argument("--title", action="append", default=[], help="Only process rows whose title contains this text (repeatable)")
    parser.add_argument("--isrc", action="append", default=[], help="Only process these ISRCs (repeatable)")
    parser.add_argument("--oldest-first", action="store_true", help="Process ascending by id instead of newest-first")
    parser.add_argument("--search-limit", type=int, default=10, help="Spotify search result limit per ISRC")
    parser.add_argument("--commit-every", type=int, default=100, help="Commit every N updates in execute mode")
    parser.add_argument("--busy-timeout-ms", type=int, default=10_000, help="SQLite busy timeout in milliseconds")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-row progress to stderr")
    args = parser.parse_args(argv)

    db_path_arg = args.db
    if db_path_arg is None:
        env_db = os.environ.get("TAGSLUT_DB")
        if env_db:
            db_path_arg = Path(env_db)
    if db_path_arg is None:
        print("error: --db is required unless TAGSLUT_DB is set", file=sys.stderr)
        return 1

    db_path = db_path_arg.expanduser().resolve()
    artist_terms = _normalized_terms(args.artist)
    title_terms = _normalized_terms(args.title)
    isrc_terms = _normalized_terms(args.isrc, upper=True)
    try:
        summary = run(
            db_path=db_path,
            execute=bool(args.execute),
            resume_from_id=int(args.resume_from_id),
            limit=args.limit,
            newest_first=not bool(args.oldest_first),
            artist_terms=artist_terms,
            title_terms=title_terms,
            isrc_terms=isrc_terms,
            search_limit=max(1, int(args.search_limit)),
            commit_every=max(1, int(args.commit_every)),
            busy_timeout_ms=max(1, int(args.busy_timeout_ms)),
            verbose=bool(args.verbose),
        )
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc()
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("interrupted"):
        print(
            f"resume with --resume-from-id {summary['next_resume_from_id']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
