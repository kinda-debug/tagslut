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
import time
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


@dataclass
class BackfillReport:
    started_at: float
    state_path: Path
    resume_from_state: bool = False
    state_source: str | None = None


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


def _rank_spotify_candidates(
    row: sqlite3.Row | dict[str, Any],
    hits: list[SpotifyTrack],
) -> CandidateSelection:
    row_artists = _artist_parts(_row_artist_name(row))
    row_title_key = _norm_title_key(_row_title_name(row))
    row_duration_ms = _row_duration_ms(row)

    unique_hits: dict[str, SpotifyTrack] = {}
    for hit in hits:
        if _norm_text(hit.spotify_id):
            unique_hits[str(hit.spotify_id)] = hit
    ordered_hits = list(unique_hits.values())
    if not ordered_hits:
        return CandidateSelection(None, "unresolved")

    scored: list[tuple[int, SpotifyTrack]] = []
    for hit in ordered_hits:
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


def _search_spotify_by_metadata(
    spotify: SpotifyMetadataClient,
    *,
    artist: str | None,
    title: str | None,
    limit: int,
) -> list[SpotifyTrack]:
    artist_text = _norm_text(artist)
    title_text = _norm_text(title)
    if not artist_text and not title_text:
        return []
    queries: list[str] = []
    if title_text and artist_text:
        queries.append(f'track:"{title_text}" artist:"{artist_text}"')
    if title_text:
        queries.append(f'track:"{title_text}"')
    if artist_text:
        queries.append(f'artist:"{artist_text}"')

    seen: set[str] = set()
    results: list[SpotifyTrack] = []
    for query in queries:
        payload = spotify._request(
            "/search",
            params={"q": query, "type": "track", "limit": max(1, int(limit))},
        )
        tracks_payload = payload.get("tracks") if isinstance(payload.get("tracks"), dict) else {}
        items = tracks_payload.get("items") if isinstance(tracks_payload, dict) else []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            track = spotify._track_from_payload(
                item,
                collection_type="search",
                collection_title=query,
                playlist_index=len(results) + 1,
            )
            if not track.spotify_id or track.spotify_id in seen:
                continue
            seen.add(track.spotify_id)
            results.append(track)
    return results


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


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _supports_color(stream: Any) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("NO_COLOR") is None


def _paint(text: str, *, color: str | None = None, bold: bool = False, dim: bool = False, enabled: bool) -> str:
    if not enabled:
        return text
    codes: list[str] = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if color is not None:
        codes.append(color)
    if not codes:
        return text
    return f"\033[{';'.join(codes)}m{text}\033[0m"


def _human_count(value: int) -> str:
    return f"{value:,}"


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _state_path_for_db(db_path: Path) -> Path:
    suffix = db_path.suffix + ".backfill_spotify_ids.json"
    return db_path.with_suffix(suffix)


def _load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _clear_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _state_signature(
    *,
    execute: bool,
    newest_first: bool,
    limit: int | None,
    m3u_paths: tuple[str, ...],
    artist_terms: tuple[str, ...],
    title_terms: tuple[str, ...],
    isrc_terms: tuple[str, ...],
    search_limit: int,
) -> dict[str, Any]:
    return {
        "execute": bool(execute),
        "newest_first": bool(newest_first),
        "limit": limit,
        "m3u_paths": list(m3u_paths),
        "artist_terms": list(artist_terms),
        "title_terms": list(title_terms),
        "isrc_terms": list(isrc_terms),
        "search_limit": int(search_limit),
    }


def _state_matches(
    state: dict[str, Any],
    *,
    execute: bool,
    newest_first: bool,
    limit: int | None,
    m3u_paths: tuple[str, ...],
    artist_terms: tuple[str, ...],
    title_terms: tuple[str, ...],
    isrc_terms: tuple[str, ...],
    search_limit: int,
) -> bool:
    expected = _state_signature(
        execute=execute,
        newest_first=newest_first,
        limit=limit,
        m3u_paths=m3u_paths,
        artist_terms=artist_terms,
        title_terms=title_terms,
        isrc_terms=isrc_terms,
        search_limit=search_limit,
    )
    for key, value in expected.items():
        if state.get(key) != value:
            return False
    return True


def _state_resume_from_id(state: dict[str, Any]) -> int:
    try:
        return int(state.get("resume_from_id") or 0)
    except Exception:
        return 0


def _read_m3u_paths(m3u_path: Path) -> list[Path]:
    out: list[Path] = []
    base_dir = m3u_path.parent
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        candidate = Path(line).expanduser()
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).expanduser()
        out.append(candidate.resolve())
    return out


def _identity_row_for_asset_path(
    conn: sqlite3.Connection,
    asset_path: str | Path,
) -> sqlite3.Row | None:
    active_order = "CASE WHEN COALESCE(al.active, 1) = 1 THEN 0 ELSE 1 END, " if _column_exists(
        conn, "asset_link", "active"
    ) else ""
    return conn.execute(
        f"""
        SELECT
            ti.id,
            ti.isrc,
            ti.spotify_id,
            ti.artist_norm,
            ti.title_norm,
            ti.canonical_artist,
            ti.canonical_title,
            ti.duration_ref_ms
        FROM asset_file af
        JOIN asset_link al ON al.asset_id = af.id
        JOIN track_identity ti ON ti.id = al.identity_id
        WHERE af.path = ?
          AND ti.merged_into_id IS NULL
          AND (ti.spotify_id IS NULL OR TRIM(ti.spotify_id) = '')
        ORDER BY {active_order} al.id ASC
        LIMIT 1
        """,
        (str(asset_path),),
    ).fetchone()


def _select_rows_for_paths(
    conn: sqlite3.Connection,
    *,
    asset_paths: tuple[Path, ...],
    resume_from_id: int,
    limit: int | None,
    newest_first: bool = True,
) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    seen_ids: set[int] = set()
    for asset_path in asset_paths:
        row = _identity_row_for_asset_path(conn, asset_path)
        if row is None:
            continue
        identity_id = int(row["id"])
        if identity_id in seen_ids:
            continue
        seen_ids.add(identity_id)
        rows.append(row)
    rows.sort(key=lambda row: int(row["id"]), reverse=newest_first)
    if resume_from_id > 0:
        if newest_first:
            rows = [row for row in rows if int(row["id"]) < resume_from_id]
        else:
            rows = [row for row in rows if int(row["id"]) > resume_from_id]
    if limit is not None:
        rows = rows[: int(limit)]
    return rows


def _emit_line(text: str, *, stream: Any, enabled: bool = True) -> None:
    print(text if enabled else _strip_ansi(text), file=stream)


def _emit_tracker(
    *,
    stream: Any,
    enabled: bool,
    processed: int,
    total: int,
    updated: int,
    unresolved: int,
    ambiguous: int,
    conflicts: int,
    errors: int,
    last_identity_id: int,
    last_isrc: str | None,
    last_status: str | None,
) -> None:
    if not enabled:
        return
    tracker = (
        f"tracker {processed}/{total} "
        f"updated={updated} unresolved={unresolved} ambiguous={ambiguous} "
        f"conflicts={conflicts} errors={errors} "
        f"last=#{last_identity_id or 0}"
    )
    if last_isrc:
        tracker += f" isrc={last_isrc}"
    if last_status:
        tracker += f" status={last_status}"
    print(f"\r\033[2K{tracker}", end="", file=stream, flush=True)


def _emit_start(
    *,
    stream: Any,
    enabled: bool,
    db_path: Path,
    mode: str,
    order: str,
    total: int,
    state_path: Path,
    resume_from_id: int,
    resumed: bool,
    state_source: str | None,
    filters: dict[str, list[str]],
) -> None:
    if resumed:
        source = f" from {state_source}" if state_source else ""
        _emit_line(
            _paint(
                f"resume{source}: continuing at id<{resume_from_id}",
                color="36",
                bold=True,
                enabled=enabled,
            ),
            stream=stream,
        )
    _emit_line(
        _paint(
            f"start: {mode} {order} total={_human_count(total)} db={db_path}",
            color="37",
            bold=True,
            enabled=enabled,
        ),
        stream=stream,
    )
    if any(filters.values()):
        _emit_line(
            _paint(
                "filters: "
                f"artist={filters['artist'] or ['(none)']} "
                f"title={filters['title'] or ['(none)']} "
                f"isrc={filters['isrc'] or ['(none)']}",
                color="36",
                enabled=enabled,
            ),
            stream=stream,
        )
    _emit_line(
        _paint(f"state: {state_path}", color="35", dim=True, enabled=enabled),
        stream=stream,
    )


def _emit_event(
    *,
    stream: Any,
    enabled: bool,
    kind: str,
    identity_id: int,
    isrc: str | None,
    message: str,
) -> None:
    palette = {
        "match": ("32", True),
        "skip": ("33", True),
        "error": ("31", True),
        "info": ("36", False),
        "state": ("35", False),
    }
    color, bold = palette.get(kind, ("37", False))
    prefix = kind.upper()
    parts = [prefix, f"#{identity_id}"]
    if isrc:
        parts.append(isrc)
    parts.append(message)
    _emit_line(
        _paint(" ".join(parts), color=color, bold=bold, enabled=enabled),
        stream=stream,
    )


def _emit_report(
    *,
    stream: Any,
    enabled: bool,
    stats: dict[str, Any],
    elapsed_s: float,
    state_path: Path,
    state_saved: bool,
) -> None:
    status = "interrupted" if stats.get("interrupted") else "completed"
    _emit_line(
        _paint(f"{status}: {_human_count(int(stats.get('processed') or 0))} rows in {_format_elapsed(elapsed_s)}", color="37", bold=True, enabled=enabled),
        stream=stream,
    )
    _emit_line(
        _paint(
            f"updated={_human_count(int(stats.get('updated') or 0))} "
            f"unresolved={_human_count(int(stats.get('unresolved') or 0))} "
            f"ambiguous={_human_count(int(stats.get('ambiguous') or 0))} "
            f"conflicts={_human_count(int(stats.get('conflicts') or 0))} "
            f"errors={_human_count(int(stats.get('errors') or 0))}",
            color="36",
            enabled=enabled,
        ),
        stream=stream,
    )
    _emit_line(
        _paint(
            f"last_id={int(stats.get('last_identity_id') or 0)} next_resume_from_id={int(stats.get('next_resume_from_id') or 0)}",
            color="35",
            enabled=enabled,
        ),
        stream=stream,
    )
    if stats.get("missing_m3u_written"):
        _emit_line(
            _paint(
                f"missing_m3u={stats['missing_m3u_written']} count={int(stats.get('missing_m3u_count') or 0)}",
                color="36",
                bold=True,
                enabled=enabled,
            ),
            stream=stream,
        )
    if state_saved:
        _emit_line(
            _paint(f"checkpoint saved: {state_path}", color="33", bold=True, enabled=enabled),
            stream=stream,
        )
    else:
        _emit_line(
            _paint(f"checkpoint cleared: {state_path}", color="32", bold=True, enabled=enabled),
            stream=stream,
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
    if not exact_hits:
        return CandidateSelection(None, "unresolved")
    if len(exact_hits) == 1:
        return CandidateSelection(
            str(exact_hits[0].spotify_id),
            "exact_isrc",
            (
                _candidate_detail(
                    exact_hits[0],
                    row_artists=_artist_parts(_row_artist_name(row)),
                    row_title_key=_norm_title_key(_row_title_name(row)),
                    row_duration_ms=_row_duration_ms(row),
                ),
            ),
        )
    return _rank_spotify_candidates(row, exact_hits)


def choose_spotify_candidate_from_metadata(
    row: sqlite3.Row | dict[str, Any],
    hits: list[SpotifyTrack],
) -> CandidateSelection:
    return _rank_spotify_candidates(row, hits)


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


def _missing_spotify_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    merged_where = "AND ti.merged_into_id IS NULL" if _column_exists(conn, "track_identity", "merged_into_id") else ""
    return conn.execute(
        f"""
        SELECT DISTINCT
            af.path AS path,
            COALESCE(ti.canonical_artist, ti.artist_norm) AS artist,
            COALESCE(ti.canonical_title, ti.title_norm) AS title
        FROM track_identity ti
        JOIN asset_link al ON al.identity_id = ti.id
        JOIN asset_file af ON af.id = al.asset_id
        WHERE (ti.spotify_id IS NULL OR TRIM(ti.spotify_id) = '')
          AND af.path IS NOT NULL
          AND TRIM(af.path) != ''
          {merged_where}
        ORDER BY af.path ASC
        """,
    ).fetchall()


def _write_missing_spotify_m3u(conn: sqlite3.Connection, output_path: Path) -> int:
    rows = _missing_spotify_rows(conn)
    lines = ["#EXTM3U", "#EXTENC: UTF-8", "#PLAYLIST:missing spotify_id"]
    for row in rows:
        artist = _norm_text(row["artist"]) or "Unknown"
        title = _norm_text(row["title"]) or Path(str(row["path"])).stem
        lines.append(f"#EXTINF:-1,{artist} - {title}")
        lines.append(str(Path(str(row["path"])).expanduser()))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


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
    resume_from_id: int | None,
    limit: int | None,
    asset_paths: tuple[Path, ...] = (),
    missing_m3u_path: Path | None = None,
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
    state_path = _state_path_for_db(db_path)
    started_at = time.monotonic()
    try:
        initial_resume_from_id = int(resume_from_id or 0)
        auto_resume = resume_from_id is None
        state = _load_state(state_path)
        resume_source: str | None = None
        effective_resume_from_id = initial_resume_from_id
        if auto_resume and state is not None and _state_matches(
            state,
            execute=execute,
            newest_first=newest_first,
            limit=limit,
            m3u_paths=tuple(str(path) for path in asset_paths),
            artist_terms=artist_terms,
            title_terms=title_terms,
            isrc_terms=isrc_terms,
            search_limit=search_limit,
        ):
            state_resume_from_id = _state_resume_from_id(state)
            if state_resume_from_id > 0 and state_resume_from_id != initial_resume_from_id:
                effective_resume_from_id = state_resume_from_id
                resume_source = str(state_path)
        if asset_paths:
            rows = _select_rows_for_paths(
                conn,
                asset_paths=asset_paths,
                resume_from_id=effective_resume_from_id,
                limit=limit,
                newest_first=newest_first,
            )
        else:
            rows = _select_rows(
                conn,
                resume_from_id=effective_resume_from_id,
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
            "resume_from_id": effective_resume_from_id,
            "next_resume_from_id": effective_resume_from_id,
            "order": "newest_first" if newest_first else "oldest_first",
            "interrupted": False,
            "interrupted_signal": None,
            "stopped_at": None,
            "filters": {
                "artist": list(artist_terms),
                "title": list(title_terms),
                "isrc": list(isrc_terms),
            },
            "source_paths": [str(path) for path in asset_paths],
            "resume_state_path": str(state_path),
            "resume_state_used": bool(resume_source),
            "missing_m3u_path": str(missing_m3u_path) if missing_m3u_path else None,
        }

        if execute:
            conn.execute("BEGIN IMMEDIATE")

        tracker_enabled = _supports_color(sys.stderr)
        _emit_start(
            stream=sys.stderr,
            enabled=tracker_enabled,
            db_path=db_path,
            mode=stats["mode"],
            order=stats["order"],
            total=len(rows),
            state_path=state_path,
            resume_from_id=effective_resume_from_id,
            resumed=bool(resume_source),
            state_source=resume_source,
            filters=stats["filters"],
        )

        with SpotifyMetadataClient() as spotify:
            for row in rows:
                if interrupt_state.requested:
                    break
                identity_id = int(row["id"])
                stats["processed"] += 1
                stats["last_identity_id"] = identity_id
                isrc = _norm_isrc(row["isrc"])
                last_status = None
                try:
                    if isrc:
                        hits = spotify.search_by_isrc(isrc, limit=search_limit)
                        selection = choose_spotify_candidate(row, hits)
                    else:
                        selection = choose_spotify_candidate_from_metadata(
                            row,
                            _search_spotify_by_metadata(
                                spotify,
                                artist=_row_artist_name(row),
                                title=_row_title_name(row),
                                limit=search_limit,
                            ),
                        )
                    if selection.spotify_id is None:
                        stats[selection.reason] = int(stats.get(selection.reason, 0)) + 1
                        last_status = "skip"
                        if verbose or tracker_enabled:
                            _emit_event(
                                stream=sys.stderr,
                                enabled=tracker_enabled,
                                kind="skip",
                                identity_id=identity_id,
                                isrc=isrc,
                                message=selection.reason if isrc else "missing_isrc_unresolved",
                            )
                        if verbose:
                            for line in _format_verbose_lines(row, selection):
                                _emit_line(line, stream=sys.stderr)
                        _emit_tracker(
                            stream=sys.stderr,
                            enabled=tracker_enabled,
                            processed=stats["processed"],
                            total=len(rows),
                            updated=stats["updated"],
                            unresolved=stats["unresolved"],
                            ambiguous=stats["ambiguous"],
                            conflicts=stats["conflicts"],
                            errors=stats["errors"],
                            last_identity_id=stats["last_identity_id"],
                            last_isrc=isrc,
                            last_status=last_status,
                        )
                        continue
                    spotify_id = selection.spotify_id
                    if _spotify_id_conflicts(conn, identity_id, spotify_id):
                        stats["conflicts"] += 1
                        last_status = "skip"
                        if verbose or tracker_enabled:
                            _emit_event(
                                stream=sys.stderr,
                                enabled=tracker_enabled,
                                kind="skip",
                                identity_id=identity_id,
                                isrc=isrc,
                                message=f"conflict on {spotify_id}",
                            )
                        _emit_tracker(
                            stream=sys.stderr,
                            enabled=tracker_enabled,
                            processed=stats["processed"],
                            total=len(rows),
                            updated=stats["updated"],
                            unresolved=stats["unresolved"],
                            ambiguous=stats["ambiguous"],
                            conflicts=stats["conflicts"],
                            errors=stats["errors"],
                            last_identity_id=stats["last_identity_id"],
                            last_isrc=isrc,
                            last_status=last_status,
                        )
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
                            stats["next_resume_from_id"] = identity_id
                            _write_state(
                                state_path,
                                {
                                    "db_path": str(db_path),
                                    "resume_from_id": stats["next_resume_from_id"],
                            **_state_signature(
                                execute=execute,
                                newest_first=newest_first,
                                limit=limit,
                                m3u_paths=tuple(str(path) for path in asset_paths),
                                artist_terms=artist_terms,
                                title_terms=title_terms,
                                isrc_terms=isrc_terms,
                                search_limit=search_limit,
                            ),
                                    "status": "checkpoint",
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                },
                            )
                    stats["updated"] += 1
                    if not execute:
                        stats["next_resume_from_id"] = identity_id
                    last_status = "match"
                    if verbose or tracker_enabled:
                        _emit_event(
                            stream=sys.stderr,
                            enabled=tracker_enabled,
                            kind="match",
                            identity_id=identity_id,
                            isrc=isrc,
                            message=f"-> {spotify_id} ({selection.reason})",
                        )
                    if verbose:
                        for line in _format_verbose_lines(row, selection):
                            _emit_line(line, stream=sys.stderr)
                except SpotifyIntakeError as exc:
                    stats["errors"] += 1
                    last_status = "error"
                    if verbose or tracker_enabled:
                        _emit_event(
                            stream=sys.stderr,
                            enabled=tracker_enabled,
                            kind="error",
                            identity_id=identity_id,
                            isrc=isrc,
                            message=str(exc),
                        )
                    _emit_tracker(
                        stream=sys.stderr,
                        enabled=tracker_enabled,
                        processed=stats["processed"],
                        total=len(rows),
                        updated=stats["updated"],
                        unresolved=stats["unresolved"],
                        ambiguous=stats["ambiguous"],
                        conflicts=stats["conflicts"],
                        errors=stats["errors"],
                        last_identity_id=stats["last_identity_id"],
                        last_isrc=isrc,
                        last_status=last_status,
                    )
                    if "rate_limited" in str(exc):
                        break
                except Exception:
                    stats["errors"] += 1
                    last_status = "error"
                    if verbose or tracker_enabled:
                        _emit_event(
                            stream=sys.stderr,
                            enabled=tracker_enabled,
                            kind="error",
                            identity_id=identity_id,
                            isrc=isrc,
                            message="unexpected exception",
                        )
                    if verbose:
                        traceback.print_exc()
                    _emit_tracker(
                        stream=sys.stderr,
                        enabled=tracker_enabled,
                        processed=stats["processed"],
                        total=len(rows),
                        updated=stats["updated"],
                        unresolved=stats["unresolved"],
                        ambiguous=stats["ambiguous"],
                        conflicts=stats["conflicts"],
                        errors=stats["errors"],
                        last_identity_id=stats["last_identity_id"],
                        last_isrc=isrc,
                        last_status=last_status,
                    )
                _emit_tracker(
                    stream=sys.stderr,
                    enabled=tracker_enabled,
                    processed=stats["processed"],
                    total=len(rows),
                    updated=stats["updated"],
                    unresolved=stats["unresolved"],
                    ambiguous=stats["ambiguous"],
                    conflicts=stats["conflicts"],
                    errors=stats["errors"],
                    last_identity_id=stats["last_identity_id"],
                    last_isrc=isrc,
                    last_status=last_status,
                )

        if execute:
            conn.commit()
        stats["interrupted"] = interrupt_state.requested
        stats["interrupted_signal"] = interrupt_state.signal_name
        stats["stopped_at"] = datetime.now(timezone.utc).isoformat()
        if stats["interrupted"]:
            _write_state(
                state_path,
                {
                    "db_path": str(db_path),
                    "resume_from_id": int(stats["next_resume_from_id"] or initial_resume_from_id),
                    **_state_signature(
                        execute=execute,
                        newest_first=newest_first,
                        limit=limit,
                        m3u_paths=tuple(str(path) for path in asset_paths),
                        artist_terms=artist_terms,
                        title_terms=title_terms,
                        isrc_terms=isrc_terms,
                        search_limit=search_limit,
                    ),
                    "status": "interrupted",
                    "updated_at": stats["stopped_at"],
                    "summary": {k: stats[k] for k in ("processed", "updated", "unresolved", "ambiguous", "conflicts", "errors", "last_identity_id", "next_resume_from_id")},
                },
            )
            stats["resume_state_saved"] = True
        else:
            if execute:
                _clear_state(state_path)
            stats["resume_state_saved"] = False
        if missing_m3u_path is not None:
            stats["missing_m3u_count"] = _write_missing_spotify_m3u(conn, missing_m3u_path)
            stats["missing_m3u_written"] = str(missing_m3u_path)
        if tracker_enabled:
            print(file=sys.stderr)
        stats["elapsed_s"] = round(time.monotonic() - started_at, 3)
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
        default=None,
        help="Resume cursor. When omitted, the last interrupted run is resumed automatically.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N eligible identities")
    parser.add_argument(
        "--m3u",
        action="append",
        default=[],
        help="Optional M3U/M3U8 file listing audio paths to backfill (repeatable)",
    )
    parser.add_argument(
        "--missing-m3u",
        type=Path,
        default=None,
        help="Write an M3U of DB tracks still missing spotify_id (defaults to <db>.missing_spotify_ids.m3u)",
    )
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
    m3u_paths = tuple(
        path.resolve()
        for raw in args.m3u
        for path in _read_m3u_paths(Path(raw).expanduser().resolve())
    )
    missing_m3u_path = (
        args.missing_m3u.expanduser().resolve()
        if args.missing_m3u is not None
        else db_path.with_name(f"{db_path.stem}.missing_spotify_ids.m3u")
    )
    try:
        summary = run(
            db_path=db_path,
            execute=bool(args.execute),
            resume_from_id=args.resume_from_id,
            limit=args.limit,
            asset_paths=m3u_paths,
            missing_m3u_path=missing_m3u_path,
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
    _emit_report(
        stream=sys.stderr,
        enabled=_supports_color(sys.stderr),
        stats=summary,
        elapsed_s=float(summary.get("elapsed_s") or 0.0),
        state_path=_state_path_for_db(db_path),
        state_saved=bool(summary.get("resume_state_saved")),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
