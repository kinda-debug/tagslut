#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, cast
from urllib.parse import quote_plus

try:
    from flask import Flask, jsonify, request, render_template_string
except ImportError as _flask_err:
    raise ImportError(
        "flask is required to run dj_review_app. "
        "Install it with: pip install 'tagslut[web]'"
    ) from _flask_err

from tagslut.dj.curation import calculate_dj_score, filter_candidates, load_dj_curation_config

_SAFE_ARTIST_DEFAULTS = [
    Path("artifacts/dj_safe_artists_overrides.txt"),
    Path("artifacts/dj_safe_artists_from_safe_copy.txt"),
]
_TRACK_OVERRIDES_PATH = Path("config/dj/track_overrides.csv")
_SAFE_EXPORT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class _SafeArtistCache(TypedDict):
    mtimes: dict[str, float]
    values: set[str]


class _TrackOverrideCache(TypedDict):
    mtime: float | None
    safe_paths: set[str]
    block_paths: set[str]
    safe_artists: set[str]


_SAFE_ARTIST_CACHE: _SafeArtistCache = {"mtimes": {}, "values": set()}
_TRACK_OVERRIDE_CACHE: _TrackOverrideCache = {
    "mtime": None,
    "safe_paths": set(),
    "block_paths": set(),
    "safe_artists": set(),
}
_AUTO_CACHE: dict[str, Any] = {"path": None, "config": None, "remixers_key": None, "remixers": set()}


APP = Flask(__name__)


def _load_db_path() -> Path:
    env_path = os.environ.get("TAGSLUT_DB")
    if env_path:
        return Path(env_path).expanduser()

    config_path = Path("config.toml")
    if config_path.exists():
        try:
            import tomllib
        except Exception:
            import tomli as tomllib  # type: ignore
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        db_path = (data.get("db") or {}).get("path")
        if db_path:
            return Path(db_path).expanduser()

    raise RuntimeError("No DB path found. Set TAGSLUT_DB or config.toml db.path")


def _resolve_db_path() -> Path:
    override = APP.config.get("DB_PATH")
    if override:
        return Path(override).expanduser()
    return _load_db_path()


def _resolve_policy_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    v8 = Path("config/dj/dj_curation_usb_v8.yaml")
    if v8.exists():
        return v8
    return Path("config/dj/dj_curation.yaml")


def _normalize_simple(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _split_artists(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _extract_remixer(title: str) -> str | None:
    text = title.strip()
    if not text:
        return None
    patterns = [
        r"\(([^)]+)\)",
        r"\[([^\]]+)\]",
        r" - ([^-]+)$",
    ]
    remix_keywords = [
        "remix",
        "edit",
        "rework",
        "re-edit",
        "refix",
        "dub",
        "dub mix",
        "extended",
        "club mix",
        "instrumental",
        "version",
        "vip",
        "bootleg",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            lower = match.lower()
            if any(kw in lower for kw in remix_keywords):
                for kw in remix_keywords:
                    if kw in lower:
                        name = lower.replace(kw, "").strip(" -–_")
                        return name.strip() if name.strip() else None
    return None


def _get_auto_config() -> Any:
    policy_path = str(_resolve_policy_path(None))
    if _AUTO_CACHE["path"] == policy_path and _AUTO_CACHE["config"] is not None:
        return _AUTO_CACHE["config"]
    config = load_dj_curation_config(policy_path)
    _AUTO_CACHE["path"] = policy_path
    _AUTO_CACHE["config"] = config
    return config


def _get_library_remixers(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute("SELECT COUNT(*), MAX(mtime) FROM files").fetchone()
    key = (row[0], row[1]) if row else (None, None)
    if _AUTO_CACHE["remixers_key"] == key:
        return cast(set[str], _AUTO_CACHE["remixers"])

    remixers: set[str] = set()
    rows = conn.execute(
        "SELECT canonical_artist FROM files WHERE canonical_artist IS NOT NULL AND canonical_artist != ''"
    ).fetchall()
    for r in rows:
        artist = str(r[0] or "")
        for part in _split_artists(artist):
            norm = _normalize_simple(part)
            if norm:
                remixers.add(norm)
    _AUTO_CACHE["remixers_key"] = key
    _AUTO_CACHE["remixers"] = remixers
    return remixers


def _auto_verdict_for_row(row: sqlite3.Row, conn: sqlite3.Connection) -> dict[str, Any]:
    config = _get_auto_config()
    remixers = _get_library_remixers(conn)

    duration = row["duration"]
    if duration is None and row["duration_measured_ms"]:
        duration = float(row["duration_measured_ms"]) / 1000.0

    track = {
        "path": row["path"],
        "artist": row["artist"],
        "title": row["title"],
        "genre": row["genre"],
        "bpm": row["bpm"] or 0,
        "key": row["musical_key"],
        "duration_sec": duration,
        "remixer": _extract_remixer(str(row["title"] or "")),
        "download_source": row["download_source"],
        "duration_status": row["duration_status"] if "duration_status" in row.keys() else None,
    }

    reasons: list[str] = []
    filtered = filter_candidates([track], config)
    if filtered.rejected_blocklist:
        reasons.append(filtered.rejected_blocklist[0].get("_rejection_reason", "blocklist"))
        return {"verdict": "not_ok", "score": None, "reasons": reasons}
    if filtered.rejected_duration:
        reasons.append(filtered.rejected_duration[0].get("_rejection_reason", "duration"))
        return {"verdict": "not_ok", "score": None, "reasons": reasons}
    if filtered.rejected_genre:
        reasons.append(filtered.rejected_genre[0].get("_rejection_reason", "genre"))
        return {"verdict": "not_ok", "score": None, "reasons": reasons}

    if filtered.flagged_reviewlist:
        reasons.append(filtered.flagged_reviewlist[0].get("_flag_reason", "artist_reviewlist"))

    track_item = filtered.passed[0] if filtered.passed else track
    override_verdict = track_item.get("_verdict")
    if override_verdict in {"safe", "block", "review"}:
        verdict = {"safe": "ok", "block": "not_ok", "review": "review"}[override_verdict]
        reasons.append(f"track_override:{override_verdict}")
        score = None
    else:
        score_result = calculate_dj_score(track_item, config, remixers)
        verdict = {"safe": "ok", "block": "not_ok", "review": "review"}[score_result.decision]
        score = score_result.score
        reasons.extend(score_result.reasons)

    # Soft demotions for incomplete/mixed metadata
    genre_value = _normalize_simple(track.get("genre") or "")
    has_dj = any(_normalize_simple(g) in genre_value for g in config.dj_genres)
    has_anti = any(_normalize_simple(g) in genre_value for g in config.anti_dj_genres)
    soft_flags: list[str] = []
    if has_dj and has_anti:
        soft_flags.append("mixed genre")
    if not track.get("bpm"):
        soft_flags.append("missing BPM")
    if not track.get("duration_sec"):
        soft_flags.append("missing duration")
    duration_status = track.get("duration_status")
    if duration_status and str(duration_status).lower() != "ok":
        soft_flags.append(f"duration {duration_status}")
    if str(track.get("download_source") or "").lower() == "legacy":
        if not genre_value or not track.get("bpm"):
            soft_flags.append("legacy + weak metadata")

    if soft_flags and verdict == "ok":
        verdict = "review"
        reasons.append("soft demote: " + ", ".join(soft_flags))

    return {"verdict": verdict, "score": score, "reasons": reasons}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_resolve_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dj_review_decisions (
            level TEXT NOT NULL,
            key TEXT NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'manual',
            PRIMARY KEY (level, key)
        );
        """
    )
    conn.commit()


def _normalize_key(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _key_for(level: str, row: sqlite3.Row) -> str:
    if level == "track":
        return str(row["path"])
    if level == "album":
        artist_key = _normalize_key(row["artist"])
        album_key = _normalize_key(row["album"])
        return f"{artist_key}|{album_key}"
    artist_key = _normalize_key(row["artist"])
    return artist_key


def _library_prefix() -> str | None:
    override = APP.config.get("LIBRARY_PREFIX")
    if override:
        return str(override)
    return os.environ.get("DJ_REVIEW_LIBRARY_PREFIX") or None


def _parse_safe_artist_files() -> list[Path]:
    override = os.environ.get("DJ_REVIEW_SAFE_ARTISTS", "").strip()
    if override:
        return [Path(p.strip()) for p in override.split(",") if p.strip()]
    return [p for p in _SAFE_ARTIST_DEFAULTS if p.exists()]


def _load_safe_artists() -> set[str]:
    paths = _parse_safe_artist_files()
    mtimes: dict[str, float] = {}
    for path in paths:
        try:
            mtimes[str(path)] = path.stat().st_mtime
        except FileNotFoundError:
            mtimes[str(path)] = 0.0
    if _SAFE_ARTIST_CACHE["mtimes"] == mtimes:
        return _SAFE_ARTIST_CACHE["values"]

    values: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw:
                continue
            if raw.startswith("# "):
                continue
            if raw.startswith("\"") and raw.endswith("\"") and len(raw) > 1:
                raw = raw[1:-1].strip()
            if raw:
                values.add(_normalize_key(raw))

    # Merge safe artists from track overrides (safe verdicts)
    overrides = _load_track_overrides()
    values.update(overrides["safe_artists"])

    _SAFE_ARTIST_CACHE["mtimes"] = mtimes
    _SAFE_ARTIST_CACHE["values"] = values
    return values


def _load_track_overrides() -> _TrackOverrideCache:
    try:
        mtime = _TRACK_OVERRIDES_PATH.stat().st_mtime
    except FileNotFoundError:
        mtime = None
    if _TRACK_OVERRIDE_CACHE["mtime"] == mtime:
        return _TRACK_OVERRIDE_CACHE

    safe_paths: set[str] = set()
    block_paths: set[str] = set()
    safe_artists: set[str] = set()

    if _TRACK_OVERRIDES_PATH.exists():
        with _TRACK_OVERRIDES_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if not row:
                    continue
                first = row[0].strip()
                if not first:
                    continue
                if first.startswith("#"):
                    continue
                while len(row) < 4:
                    row.append("")
                path = row[0].strip()
                artist = row[1].strip()
                verdict = row[3].strip().lower()
                if verdict == "safe":
                    if path:
                        safe_paths.add(path)
                    if artist:
                        safe_artists.add(_normalize_key(artist))
                elif verdict == "block":
                    if path:
                        block_paths.add(path)

    _TRACK_OVERRIDE_CACHE.update(
        {
            "mtime": mtime,
            "safe_paths": safe_paths,
            "block_paths": block_paths,
            "safe_artists": safe_artists,
        }
    )
    return _TRACK_OVERRIDE_CACHE


def _search_clause(query: str, fields: list[str]) -> tuple[str, list[Any]]:
    if not query:
        return "", []
    like = f"%{query}%"
    clause = " OR ".join([f"{field} LIKE ?" for field in fields])
    # Return only the clause body; callers are responsible for adding any
    # surrounding boolean operators such as "AND (" / ")".
    return clause, [like] * len(fields)


def _bucket_clause(bucket: str) -> str:
    if bucket == "ok":
        return "d.status = 'ok'"
    return "d.status IS NULL OR d.status = 'not_ok'"


def _fetch_artist_items(bucket: str, query: str, limit: int, offset: int) -> list[dict[str, Any]]:
    prefix = _library_prefix()
    safe_artists = _load_safe_artists()
    conn = _get_conn()
    try:
        _ensure_schema(conn)
        search_clause, params = _search_clause(query, ["artist"])
        prefix_clause = ""
        prefix_params: list[Any] = []
        if prefix:
            prefix_clause = " AND path LIKE ?"
            prefix_params.append(f"{prefix}%")

        sql = f"""
            WITH base AS (
                SELECT
                    lower(trim(coalesce(canonical_artist, ''))) AS artist_key,
                    coalesce(canonical_artist, '') AS artist,
                    COUNT(*) AS track_count
                FROM files
                WHERE coalesce(canonical_artist, '') != ''
                {prefix_clause}
                GROUP BY artist_key, artist
            )
            SELECT base.artist_key, base.artist, base.track_count, d.status
            FROM base
            LEFT JOIN dj_review_decisions d
                ON d.level = 'artist' AND d.key = base.artist_key
            WHERE 1=1
            {search_clause}
            ORDER BY base.artist;
        """
        rows = conn.execute(sql, prefix_params + params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            status = row["status"]
            if status is None and row["artist_key"] in safe_artists:
                status = "ok"
            if bucket == "ok" and status != "ok":
                continue
            if bucket != "ok" and status == "ok":
                continue
            items.append(
                {
                    "key": row["artist_key"],
                    "label": row["artist"],
                    "count": row["track_count"],
                    "status": status or "unreviewed",
                }
            )
        return items[offset : offset + limit]
    finally:
        conn.close()


def _fetch_album_items(bucket: str, query: str, limit: int, offset: int) -> list[dict[str, Any]]:
    prefix = _library_prefix()
    safe_artists = _load_safe_artists()
    conn = _get_conn()
    try:
        _ensure_schema(conn)
        search_clause, params = _search_clause(query, ["artist", "album"])
        prefix_clause = ""
        prefix_params: list[Any] = []
        if prefix:
            prefix_clause = " AND path LIKE ?"
            prefix_params.append(f"{prefix}%")

        sql = f"""
            WITH base AS (
                SELECT
                    lower(trim(coalesce(canonical_artist, ''))) AS artist_key,
                    lower(trim(coalesce(canonical_album, ''))) AS album_key,
                    coalesce(canonical_artist, '') AS artist,
                    coalesce(canonical_album, '') AS album,
                    COUNT(*) AS track_count
                FROM files
                WHERE coalesce(canonical_artist, '') != ''
                  AND coalesce(canonical_album, '') != ''
                {prefix_clause}
                GROUP BY artist_key, album_key, artist, album
            )
            SELECT base.artist_key, base.album_key, base.artist, base.album, base.track_count, d.status
            FROM base
            LEFT JOIN dj_review_decisions d
                ON d.level = 'album' AND d.key = (base.artist_key || '|' || base.album_key)
            WHERE 1=1
            {search_clause}
            ORDER BY base.artist, base.album;
        """
        rows = conn.execute(sql, prefix_params + params).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            status = row["status"]
            if status is None and row["artist_key"] in safe_artists:
                status = "ok"
            if bucket == "ok" and status != "ok":
                continue
            if bucket != "ok" and status == "ok":
                continue
            items.append(
                {
                    "key": f"{row['artist_key']}|{row['album_key']}",
                    "label": f"{row['artist']} — {row['album']}",
                    "count": row["track_count"],
                    "status": status or "unreviewed",
                }
            )
        return items[offset : offset + limit]
    finally:
        conn.close()


def _fetch_track_items(
    bucket: str,
    query: str,
    limit: int,
    offset: int,
    *,
    auto_filter: str | None = None,
    genre_filter: str | None = None,
    source_filter: str | None = None,
    bpm_min: float | None = None,
    bpm_max: float | None = None,
    dur_min: float | None = None,
    dur_max: float | None = None,
    mismatch_only: bool = False,
) -> list[dict[str, Any]]:
    prefix = _library_prefix()
    overrides = _load_track_overrides()
    safe_paths = overrides["safe_paths"]
    block_paths = overrides["block_paths"]
    conn = _get_conn()
    try:
        _ensure_schema(conn)
        search_clause, params = _search_clause(
            query, ["canonical_artist", "canonical_album", "canonical_title", "path"]
        )
        prefix_clause = ""
        prefix_params: list[Any] = []
        if prefix:
            prefix_clause = " AND path LIKE ?"
            prefix_params.append(f"{prefix}%")

        if bucket == "ok":
            ok_paths: set[str] = set()
            decisions = conn.execute(
                "SELECT key, status FROM dj_review_decisions WHERE level = 'track'"
            ).fetchall()
            decision_map = {row["key"]: row["status"] for row in decisions}
            for path in safe_paths:
                if decision_map.get(path) is None:
                    ok_paths.add(path)
            for key, status in decision_map.items():
                if status == "ok":
                    ok_paths.add(key)

            if prefix:
                ok_paths = {p for p in ok_paths if p.startswith(prefix)}

            if not ok_paths:
                return []

            ok_items: list[dict[str, Any]] = []
            ok_list = list(ok_paths)
            chunk_size = 500
            for idx in range(0, len(ok_list), chunk_size):
                chunk = ok_list[idx : idx + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                sql = f"""
                    SELECT
                        f.path,
                        coalesce(f.canonical_artist, '') AS artist,
                        coalesce(f.canonical_album, '') AS album,
                        coalesce(f.canonical_title, '') AS title,
                        coalesce(f.canonical_genre, '') AS genre,
                        f.canonical_bpm AS bpm,
                        f.canonical_key AS musical_key,
                        f.canonical_energy AS energy,
                        f.canonical_danceability AS danceability,
                        f.duration AS duration,
                        f.duration_measured_ms AS duration_measured_ms,
                        f.duration_status AS duration_status,
                        f.download_source AS download_source
                    FROM files f
                    WHERE f.path IN ({placeholders})
                """
                rows = conn.execute(sql, chunk).fetchall()
                for row in rows:
                    label = row["title"] or Path(row["path"]).stem
                    artist = row["artist"] or "Unknown Artist"
                    text = f"{artist} {label} {row['path']}".lower()
                    if query and query.lower() not in text:
                        continue
                    auto = _auto_verdict_for_row(row, conn)
                    if auto_filter and auto.get("verdict") != auto_filter:
                        continue
                    if genre_filter:
                        if genre_filter.lower() not in str(row["genre"] or "").lower():
                            continue
                    if source_filter:
                        if source_filter.lower() != str(row["download_source"] or "").lower():
                            continue
                    bpm_val = row["bpm"]
                    if bpm_min is not None:
                        if bpm_val is None or bpm_val < bpm_min:
                            continue
                    if bpm_max is not None:
                        if bpm_val is None or bpm_val > bpm_max:
                            continue
                    duration = row["duration"]
                    if duration is None and row["duration_measured_ms"]:
                        duration = float(row["duration_measured_ms"]) / 1000.0
                    if dur_min is not None:
                        if duration is None or duration < dur_min:
                            continue
                    if dur_max is not None:
                        if duration is None or duration > dur_max:
                            continue
                    if mismatch_only:
                        manual_status = "ok"
                        if manual_status != auto.get("verdict"):
                            pass
                        else:
                            continue
                    ok_items.append(
                        {
                            "key": row["path"],
                            "label": f"{artist} — {label}",
                            "count": None,
                            "status": "ok",
                            "auto_verdict": auto.get("verdict"),
                            "auto_score": auto.get("score"),
                            "auto_reasons": auto.get("reasons"),
                        }
                    )
            ok_items.sort(key=lambda item: item["label"].lower())
            return ok_items[offset : offset + limit]

        search_sql = f" AND ({search_clause})" if search_clause else ""
        sql = f"""
            SELECT
                f.path,
                coalesce(f.canonical_artist, '') AS artist,
                coalesce(f.canonical_album, '') AS album,
                coalesce(f.canonical_title, '') AS title,
                coalesce(f.canonical_genre, '') AS genre,
                f.canonical_bpm AS bpm,
                f.canonical_key AS musical_key,
                f.canonical_energy AS energy,
                f.canonical_danceability AS danceability,
                f.duration AS duration,
                f.duration_measured_ms AS duration_measured_ms,
                f.duration_status AS duration_status,
                f.download_source AS download_source,
                d.status AS status
            FROM files f
            LEFT JOIN dj_review_decisions d
                ON d.level = 'track' AND d.key = f.path
            WHERE 1=1
              {prefix_clause}
              {search_sql}
            ORDER BY f.mtime DESC
            LIMIT ? OFFSET ?;
        """
        params = prefix_params + params + [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        track_items: list[dict[str, Any]] = []
        for row in rows:
            status = row["status"]
            if status is None:
                if row["path"] in safe_paths:
                    status = "ok"
                elif row["path"] in block_paths:
                    status = "not_ok"
            if status == "ok":
                continue
            label = row["title"] or Path(row["path"]).stem
            artist = row["artist"] or "Unknown Artist"
            auto = _auto_verdict_for_row(row, conn)
            if auto_filter and auto.get("verdict") != auto_filter:
                continue
            if genre_filter:
                if genre_filter.lower() not in str(row["genre"] or "").lower():
                    continue
            if source_filter:
                if source_filter.lower() != str(row["download_source"] or "").lower():
                    continue
            bpm_val = row["bpm"]
            if bpm_min is not None:
                if bpm_val is None or bpm_val < bpm_min:
                    continue
            if bpm_max is not None:
                if bpm_val is None or bpm_val > bpm_max:
                    continue
            duration = row["duration"]
            if duration is None and row["duration_measured_ms"]:
                duration = float(row["duration_measured_ms"]) / 1000.0
            if dur_min is not None:
                if duration is None or duration < dur_min:
                    continue
            if dur_max is not None:
                if duration is None or duration > dur_max:
                    continue
            if mismatch_only and status in {"ok", "not_ok"}:
                if status == auto.get("verdict"):
                    continue
            track_items.append(
                {
                    "key": row["path"],
                    "label": f"{artist} — {label}",
                    "count": None,
                    "status": status or "unreviewed",
                    "auto_verdict": auto.get("verdict"),
                    "auto_score": auto.get("score"),
                    "auto_reasons": auto.get("reasons"),
                }
            )
        return track_items
    finally:
        conn.close()


def _search_links(query: str) -> list[dict[str, str]]:
    if not query:
        return []
    q = quote_plus(query)
    return [
        {"label": "Google", "url": f"https://www.google.com/search?q={q}"},
        {"label": "Beatport", "url": f"https://www.google.com/search?q=site:beatport.com+{q}"},
        {"label": "Resident Advisor", "url": f"https://www.google.com/search?q=site:ra.co+{q}"},
        {"label": "RateYourMusic", "url": f"https://www.google.com/search?q=site:rateyourmusic.com+{q}"},
        {"label": "Discogs", "url": f"https://www.google.com/search?q=site:discogs.com+{q}"},
        {"label": "Bandcamp", "url": f"https://www.google.com/search?q=site:bandcamp.com+{q}"},
        {"label": "YouTube", "url": f"https://www.google.com/search?q=site:youtube.com+{q}"},
        {"label": "Spotify", "url": f"https://www.google.com/search?q=site:open.spotify.com+{q}"},
        {"label": "Apple Music", "url": f"https://www.google.com/search?q=site:music.apple.com+{q}"},
    ]


def _evidence_for_track(conn: sqlite3.Connection, path: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            path,
            coalesce(canonical_artist, '') AS artist,
            coalesce(canonical_album, '') AS album,
            coalesce(canonical_title, '') AS title,
            coalesce(canonical_genre, '') AS genre,
            canonical_bpm AS bpm,
            canonical_key AS musical_key,
            canonical_energy AS energy,
            canonical_danceability AS danceability,
            duration,
            duration_measured_ms,
            duration_status,
            download_source
        FROM files
        WHERE path = ?
        """,
        (path,),
    ).fetchone()
    if not row:
        return {"error": "Track not found"}

    duration = row["duration"]
    if duration is None and row["duration_measured_ms"]:
        duration = float(row["duration_measured_ms"]) / 1000.0

    query = " ".join(filter(None, [row["artist"], row["title"], row["album"]]))
    auto = _auto_verdict_for_row(row, conn)

    return {
        "title": row["title"],
        "artist": row["artist"],
        "album": row["album"],
        "genre": row["genre"],
        "bpm": row["bpm"],
        "key": row["musical_key"],
        "energy": row["energy"],
        "danceability": row["danceability"],
        "duration": duration,
        "duration_status": row["duration_status"],
        "download_source": row["download_source"],
        "path": row["path"],
        "links": _search_links(query),
        "auto": auto,
    }


def _evidence_for_album(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    artist_key, _, album_key = key.partition("|")
    row = conn.execute(
        """
        SELECT
            coalesce(canonical_artist, '') AS artist,
            coalesce(canonical_album, '') AS album,
            COUNT(*) AS track_count
        FROM files
        WHERE lower(trim(coalesce(canonical_artist, ''))) = ?
          AND lower(trim(coalesce(canonical_album, ''))) = ?
        GROUP BY artist, album
        """,
        (artist_key, album_key),
    ).fetchone()
    if not row:
        return {"error": "Album not found"}

    query = " ".join(filter(None, [row["artist"], row["album"]]))
    return {
        "artist": row["artist"],
        "album": row["album"],
        "track_count": row["track_count"],
        "links": _search_links(query),
    }


def _evidence_for_artist(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            coalesce(canonical_artist, '') AS artist,
            COUNT(*) AS track_count
        FROM files
        WHERE lower(trim(coalesce(canonical_artist, ''))) = ?
        GROUP BY artist
        """,
        (key,),
    ).fetchone()
    if not row:
        return {"error": "Artist not found"}

    query = row["artist"]
    return {
        "artist": row["artist"],
        "track_count": row["track_count"],
        "links": _search_links(query),
    }


def index() -> str:
    return str(render_template_string(_HTML))


def items() -> Any:
    level = request.args.get("level", "track")
    bucket = request.args.get("bucket", "not_ok")
    query = (request.args.get("q") or "").strip()
    limit = int(request.args.get("limit", "200"))
    offset = int(request.args.get("offset", "0"))

    if level == "artist":
        data = _fetch_artist_items(bucket, query, limit, offset)
    elif level == "album":
        data = _fetch_album_items(bucket, query, limit, offset)
    else:
        auto_filter = (request.args.get("auto") or "").strip().lower() or None
        genre_filter = (request.args.get("genre") or "").strip() or None
        source_filter = (request.args.get("source") or "").strip() or None
        bpm_min = request.args.get("bpm_min")
        bpm_max = request.args.get("bpm_max")
        dur_min = request.args.get("dur_min")
        dur_max = request.args.get("dur_max")
        mismatch_only = request.args.get("mismatch", "").strip() in {"1", "true", "yes"}

        def _to_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except Exception:
                return None

        data = _fetch_track_items(
            bucket,
            query,
            limit,
            offset,
            auto_filter=auto_filter,
            genre_filter=genre_filter,
            source_filter=source_filter,
            bpm_min=_to_float(bpm_min),
            bpm_max=_to_float(bpm_max),
            dur_min=_to_float(dur_min),
            dur_max=_to_float(dur_max),
            mismatch_only=mismatch_only,
        )

    return jsonify({"items": data})


def move() -> Any:
    payload = request.get_json(force=True) or {}
    level = payload.get("level")
    keys = payload.get("keys") or []
    status = payload.get("status")
    if level not in {"artist", "album", "track"}:
        return jsonify({"error": "invalid level"}), 400
    if status not in {"ok", "not_ok"}:
        return jsonify({"error": "invalid status"}), 400
    if not keys:
        return jsonify({"updated": 0})

    conn = _get_conn()
    try:
        _ensure_schema(conn)
        now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        for key in keys:
            conn.execute(
                """
                INSERT INTO dj_review_decisions (level, key, status, updated_at, source)
                VALUES (?, ?, ?, ?, 'manual')
                ON CONFLICT(level, key) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    source = 'manual'
                """,
                (level, key, status, now),
            )
        conn.commit()
    finally:
        conn.close()

    return jsonify({"updated": len(keys)})


def evidence() -> Any:
    level = request.args.get("level", "track")
    key = request.args.get("key") or ""
    conn = _get_conn()
    try:
        _ensure_schema(conn)
        if level == "artist":
            data = _evidence_for_artist(conn, key)
        elif level == "album":
            data = _evidence_for_album(conn, key)
        else:
            data = _evidence_for_track(conn, key)
    finally:
        conn.close()
    return jsonify(data)


def _collect_ok_paths(conn: sqlite3.Connection, *, limit: int, prefix: str | None) -> list[str]:
    overrides = _load_track_overrides()
    safe_paths = overrides["safe_paths"]
    block_paths = overrides["block_paths"]
    safe_artists = _load_safe_artists()
    prefix_clause = ""
    prefix_params: list[Any] = []
    if prefix:
        prefix_clause = " AND f.path LIKE ?"
        prefix_params.append(f"{prefix}%")

    sql = f"""
        SELECT f.path,
               lower(trim(coalesce(f.canonical_artist, ''))) AS artist_key,
               lower(trim(coalesce(f.canonical_album, ''))) AS album_key,
               d_track.status AS track_status,
               d_album.status AS album_status,
               d_artist.status AS artist_status
        FROM files f
        LEFT JOIN dj_review_decisions d_track
            ON d_track.level = 'track' AND d_track.key = f.path
        LEFT JOIN dj_review_decisions d_album
            ON d_album.level = 'album'
            AND d_album.key = (
                lower(trim(coalesce(f.canonical_artist, '')))
                || '|'
                || lower(trim(coalesce(f.canonical_album, '')))
            )
        LEFT JOIN dj_review_decisions d_artist
            ON d_artist.level = 'artist'
            AND d_artist.key = lower(trim(coalesce(f.canonical_artist, '')))
        WHERE 1=1
        {prefix_clause}
        ORDER BY f.mtime DESC
    """
    rows = conn.execute(sql, prefix_params).fetchall()
    paths: list[str] = []
    for row in rows:
        status = row["track_status"]
        if status is None:
            if row["path"] in safe_paths:
                status = "ok"
            elif row["path"] in block_paths:
                status = "not_ok"
        if status is None:
            status = row["album_status"] or row["artist_status"]
        if status is None and row["artist_key"] in safe_artists:
            status = "ok"
        if status == "ok":
            paths.append(row["path"])
            if limit and len(paths) >= limit:
                break
    return paths


def _write_m3u(path: Path, items: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(items) + ("\n" if items else ""), encoding="utf-8")


def export() -> Any:
    payload = request.get_json(force=True) or {}
    output = payload.get("output") or "artifacts/dj_review_ok.m3u8"
    limit = int(payload.get("limit", "0"))
    output_path = Path(output)

    conn = _get_conn()
    try:
        _ensure_schema(conn)
        paths = _collect_ok_paths(conn, limit=limit, prefix=_library_prefix())
        _write_m3u(output_path, paths)
    finally:
        conn.close()

    return jsonify({"output": str(output_path), "count": len(paths)})


def _validate_usb_path(usb_path: str) -> str:
    """
    Validate a user-supplied USB path before passing it to a subprocess.

    The path must be absolute and must not contain null bytes.
    Additional project-specific checks (such as restricting to a mount
    point prefix) can be added here if desired.
    """
    if "\x00" in usb_path:
        raise ValueError("usb_path contains invalid characters")
    if not os.path.isabs(usb_path):
        raise ValueError("usb_path must be an absolute path")
    # Restrict USB paths to common mount locations to avoid arbitrary paths.
    allowed_prefixes = (os.path.sep + "media", os.path.sep + "mnt")
    if not usb_path.startswith(allowed_prefixes):
        raise ValueError("usb_path must be under a mounted USB directory")
    return usb_path


def _validate_output_path(output_m3u: str) -> Path:
    """
    Validate and normalize a user-supplied output playlist path.

    The resulting path is forced to live under a local 'artifacts' directory
    adjacent to this module, preventing directory traversal.

    Only a filename (no directory components) is honored from user input.
    """
    if "\x00" in output_m3u:
        raise ValueError("output_m3u contains invalid characters")
    raw_name = output_m3u.strip()
    if not raw_name:
        raise ValueError("output_m3u must be a non-empty filename")
    if Path(raw_name).name != raw_name:
        raise ValueError("output_m3u must not contain directory components")
    if not _SAFE_EXPORT_NAME_RE.fullmatch(raw_name):
        raise ValueError("output_m3u must be a simple filename using letters, numbers, . _ or -")
    if not raw_name.lower().endswith((".m3u", ".m3u8")):
        raise ValueError("output_m3u must end with .m3u or .m3u8")

    base_dir = Path(__file__).resolve().parent / "artifacts"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / raw_name


def export_usb() -> Any:
    payload = request.get_json(force=True) or {}
    usb_path = str(payload.get("usb_path") or "").strip()
    if not usb_path:
        return jsonify({"error": "usb_path is required"}), 400

    try:
        usb_path = _validate_usb_path(usb_path)
    except ValueError as exc:
        APP.logger.info("Rejected export_usb request with invalid usb_path: %s", exc)
        return jsonify({"error": "Invalid usb_path"}), 400

    policy_path = str(payload.get("policy_path") or "").strip() or None
    output_m3u = str(payload.get("output_m3u") or "dj_review_ok.m3u8")
    limit = int(payload.get("limit", "0"))
    jobs = int(payload.get("jobs", "4"))
    overwrite = bool(payload.get("overwrite", False))
    pioneer_finalize = payload.get("pioneer_finalize", True)
    artwork_max_kb = int(payload.get("artwork_max_kb", "500"))
    rekordbox_xml = str(payload.get("rekordbox_xml") or "rekordbox.xml")

    try:
        output_path = _validate_output_path(output_m3u)
    except ValueError as exc:
        APP.logger.info("Rejected export_usb request with invalid output_m3u: %s", exc)
        return jsonify({"error": "Invalid output_m3u"}), 400

    conn = _get_conn()
    try:
        _ensure_schema(conn)
        paths = _collect_ok_paths(conn, limit=limit, prefix=_library_prefix())
        _write_m3u(output_path, paths)
    finally:
        conn.close()

    sync_script = Path(__file__).resolve().parents[1] / "tools" / "dj_usb_sync.py"
    policy = _resolve_policy_path(policy_path)

    cmd = [
        sys.executable,
        str(sync_script),
        "--source",
        str(output_path),
        "--usb",
        usb_path,
        "--policy",
        str(policy),
        "--jobs",
        str(jobs),
    ]
    if overwrite:
        cmd.append("--overwrite")
    if not pioneer_finalize:
        cmd.append("--no-pioneer-finalize")
    if artwork_max_kb >= 0:
        cmd.extend(["--artwork-max-kb", str(artwork_max_kb)])
    if rekordbox_xml:
        cmd.extend(["--rekordbox-xml", rekordbox_xml])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    return jsonify(
        {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "m3u": str(output_path),
            "count": len(paths),
        }
    )


_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Tagslut DJ Review</title>
  <style>
    @import url(
      "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap"
    );
    :root {
      color-scheme: light;
      --bg: #f2efe7;
      --panel: #fffdf9;
      --ink: #201f1a;
      --muted: #6c675c;
      --accent: #0b6f68;
      --accent-2: #c1632f;
      --border: #e0d8cb;
      --shadow: 0 12px 30px rgba(32, 31, 26, 0.08);
    }
    * {
      box-sizing: border-box;
    }
    body {
      font-family: "Space Grotesk", sans-serif;
      margin: 0;
      background:
        radial-gradient(circle at 10% 10%, rgba(193, 99, 47, 0.12), transparent 40%),
        radial-gradient(circle at 90% 0%, rgba(11, 111, 104, 0.12), transparent 45%),
        linear-gradient(180deg, #f7f3eb 0%, #f0ebe2 100%);
      color: var(--ink);
      min-height: 100vh;
    }
    header {
      padding: 20px 28px;
      border-bottom: 1px solid var(--border);
      background: var(--panel);
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: var(--shadow);
      position: sticky;
      top: 0;
      z-index: 5;
    }
    header h1 {
      margin: 0;
      font-family: "Fraunces", serif;
      font-size: 22px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    header span {
      font-size: 12px;
      color: var(--muted);
    }
    .tabs {
      display: flex;
      gap: 10px;
      padding: 16px 28px 0;
    }
    .tabs button {
      border: 1px solid var(--border);
      background: var(--panel);
      padding: 8px 16px;
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      font-size: 11px;
      border-radius: 999px;
      transition: all 0.2s ease;
    }
    .tabs button.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      box-shadow: 0 8px 18px rgba(11, 111, 104, 0.25);
    }
    .layout {
      display: grid;
      grid-template-columns: 1fr 80px 1fr 320px;
      gap: 18px;
      padding: 18px 28px 36px;
      animation: fadeIn 0.4s ease;
    }
    .filter-bar {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      padding: 12px 28px 0;
    }
    .filter-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 8px 10px;
      border-radius: 12px;
      box-shadow: var(--shadow);
    }
    .filter-group label {
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .filter-group input,
    .filter-group select {
      padding: 6px 8px;
      border: 1px solid var(--border);
      background: #fbf9f4;
      font-size: 12px;
      border-radius: 8px;
    }
    .filter-group.inline {
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 14px 14px 12px;
      min-height: 420px;
      display: flex;
      flex-direction: column;
      border-radius: 14px;
      box-shadow: var(--shadow);
    }
    .panel h2 {
      margin: 0 0 8px;
      font-size: 13px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .panel .count {
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 8px;
    }
    select {
      flex: 1;
      width: 100%;
      min-height: 360px;
      border: 1px solid var(--border);
      background: #fbf9f4;
      border-radius: 10px;
      padding: 6px;
    }
    select:focus {
      outline: 2px solid rgba(11, 111, 104, 0.3);
      border-color: var(--accent);
    }
    .controls {
      display: flex;
      flex-direction: column;
      gap: 14px;
      align-items: center;
      justify-content: center;
    }
    .controls button {
      width: 54px;
      height: 54px;
      border-radius: 999px;
      border: none;
      background: linear-gradient(135deg, var(--accent), #109e94);
      color: white;
      font-size: 20px;
      cursor: pointer;
      box-shadow: 0 10px 18px rgba(11, 111, 104, 0.3);
      transition: transform 0.15s ease;
    }
    .controls button:hover {
      transform: translateY(-2px);
    }
    .filters {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 12px;
    }
    .filters input {
      flex: 1;
      padding: 7px 10px;
      border: 1px solid var(--border);
      background: #fbf9f4;
      border-radius: 8px;
      font-size: 12px;
    }
    .filters button {
      padding: 7px 12px;
      border: 1px solid var(--border);
      background: var(--panel);
      cursor: pointer;
      border-radius: 8px;
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .evidence {
      font-size: 12px;
      color: var(--ink);
      line-height: 1.4;
    }
    .evidence h3 {
      margin: 0 0 6px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      color: var(--muted);
    }
    .evidence .meta {
      margin-bottom: 10px;
      color: var(--muted);
    }
    .links a {
      display: block;
      color: var(--accent);
      text-decoration: none;
      margin-bottom: 4px;
    }
    .export-panel {
      margin-top: 14px;
      padding-top: 12px;
      border-top: 1px dashed var(--border);
    }
    .export-row {
      display: grid;
      gap: 6px;
      margin-bottom: 8px;
    }
    .export-row label {
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .export-row input[type="text"],
    .export-row input[type="number"] {
      width: 100%;
      padding: 6px 8px;
      border: 1px solid var(--border);
      background: #fbf9f4;
      font-size: 12px;
      border-radius: 8px;
    }
    .export-inline {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .export-inline label {
      display: flex;
      align-items: center;
      gap: 6px;
      text-transform: none;
      letter-spacing: 0;
    }
    .export-actions button {
      width: 100%;
      padding: 9px 10px;
      background: linear-gradient(135deg, var(--accent-2), #e27c47);
      color: white;
      border: none;
      cursor: pointer;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      border-radius: 8px;
      box-shadow: 0 10px 18px rgba(193, 99, 47, 0.25);
    }
    .export-status {
      margin-top: 8px;
      padding: 8px;
      border: 1px solid var(--border);
      background: #f7f2e8;
      min-height: 60px;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      color: var(--ink);
      border-radius: 8px;
    }
    .footer {
      padding: 0 28px 28px;
      color: var(--muted);
      font-size: 12px;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body>
  <header>
    <h1>DJ Review Console</h1>
    <span>DB: {{ db_path }}</span>
  </header>
  <div class="tabs">
    <button class="tab active" data-level="artist">Artist</button>
    <button class="tab" data-level="album">Album</button>
    <button class="tab" data-level="track">Track</button>
  </div>
  <div class="filter-bar" id="track-filters">
    <div class="filter-group">
      <label for="filter-auto">Auto Verdict</label>
      <select id="filter-auto">
        <option value="">Any</option>
        <option value="ok">OK</option>
        <option value="review">Review</option>
        <option value="not_ok">Not OK</option>
      </select>
    </div>
    <div class="filter-group">
      <label for="filter-genre">Genre Contains</label>
      <input id="filter-genre" type="text" placeholder="techno, house..." />
    </div>
    <div class="filter-group">
      <label for="filter-source">Source</label>
      <select id="filter-source">
        <option value="">Any</option>
        <option value="beatport">beatport</option>
        <option value="tidal">tidal</option>
        <option value="qobuz">qobuz</option>
        <option value="bpdl">bpdl</option>
        <option value="legacy">legacy</option>
      </select>
    </div>
    <div class="filter-group">
      <label for="filter-bpm-min">BPM Min / Max</label>
      <div class="export-inline">
        <input id="filter-bpm-min" type="number" min="0" placeholder="min" />
        <input id="filter-bpm-max" type="number" min="0" placeholder="max" />
      </div>
    </div>
    <div class="filter-group">
      <label for="filter-dur-min">Duration (s) Min / Max</label>
      <div class="export-inline">
        <input id="filter-dur-min" type="number" min="0" placeholder="min" />
        <input id="filter-dur-max" type="number" min="0" placeholder="max" />
      </div>
    </div>
    <div class="filter-group inline">
      <label for="filter-mismatch">Mismatch Only</label>
      <input id="filter-mismatch" type="checkbox" />
    </div>
  </div>
  <div class="layout">
    <div class="panel">
      <div class="filters">
        <input id="search-ok" placeholder="Search" />
        <button id="reload-ok">Reload</button>
      </div>
      <h2>OK</h2>
      <div class="count" id="count-ok">0</div>
      <select id="list-ok" multiple></select>
    </div>
    <div class="controls">
      <button id="to-ok" title="Move to OK">→</button>
      <button id="to-not" title="Move to Not OK">←</button>
    </div>
    <div class="panel">
      <div class="filters">
        <input id="search-not" placeholder="Search" />
        <button id="reload-not">Reload</button>
      </div>
      <h2>Not OK</h2>
      <div class="count" id="count-not">0</div>
      <select id="list-not" multiple></select>
    </div>
    <div class="panel">
      <h2>Evidence</h2>
      <div class="evidence">
        <div id="evidence-body">
          <div class="meta">Select an item to view web links and metadata.</div>
        </div>
        <div class="export-panel">
          <h3>Export OK → USB</h3>
          <div class="export-row">
            <label for="export-usb-path">USB Path</label>
            <input id="export-usb-path" type="text" value="{{ default_usb }}" />
          </div>
          <div class="export-row">
            <label for="export-policy-path">Policy Path</label>
            <input id="export-policy-path" type="text" value="{{ default_policy }}" />
          </div>
          <div class="export-row export-inline">
            <label for="export-jobs">Jobs</label>
            <input id="export-jobs" type="number" min="1" value="{{ default_jobs }}" />
            <label for="export-artwork">Artwork Max KB</label>
            <input id="export-artwork" type="number" min="0" value="{{ default_artwork }}" />
          </div>
          <div class="export-row export-inline">
            <label><input id="export-overwrite" type="checkbox" />Overwrite</label>
            <label><input id="export-finalize" type="checkbox" checked />Pioneer finalize</label>
          </div>
          <div class="export-row">
            <label for="export-rekordbox">Rekordbox XML</label>
            <input id="export-rekordbox" type="text" value="{{ default_rekordbox }}" />
          </div>
          <div class="export-actions">
            <button id="export-usb">Export OK → USB</button>
          </div>
          <div class="export-status" id="export-status">Idle</div>
        </div>
      </div>
    </div>
  </div>
  <div class="footer">
    Use arrows to move selected items. Decisions are stored in the DB table `dj_review_decisions`.
  </div>

<script>
const state = {
  level: 'artist',
  ok: [],
  notOk: [],
};

async function fetchItems(bucket, query) {
  const params = new URLSearchParams({
    level: state.level,
    bucket,
    q: query || '',
    limit: '200',
    offset: '0'
  });
  if (state.level === 'track') {
    const filters = getFilters();
    if (filters.auto) params.set('auto', filters.auto);
    if (filters.genre) params.set('genre', filters.genre);
    if (filters.source) params.set('source', filters.source);
    if (filters.bpmMin) params.set('bpm_min', filters.bpmMin);
    if (filters.bpmMax) params.set('bpm_max', filters.bpmMax);
    if (filters.durMin) params.set('dur_min', filters.durMin);
    if (filters.durMax) params.set('dur_max', filters.durMax);
    if (filters.mismatch) params.set('mismatch', '1');
  }
  const resp = await fetch(`/api/items?${params.toString()}`);
  const data = await resp.json();
  return data.items || [];
}

function renderList(listEl, items) {
  listEl.innerHTML = '';
  items.forEach(item => {
    const opt = document.createElement('option');
    opt.value = item.key;
    opt.textContent = item.count ? `${item.label} (${item.count})` : item.label;
    opt.dataset.status = item.status;
    listEl.appendChild(opt);
  });
}

async function loadLists() {
  const okQuery = document.getElementById('search-ok').value.trim();
  const notQuery = document.getElementById('search-not').value.trim();
  state.ok = await fetchItems('ok', okQuery);
  state.notOk = await fetchItems('not_ok', notQuery);
  renderList(document.getElementById('list-ok'), state.ok);
  renderList(document.getElementById('list-not'), state.notOk);
  document.getElementById('count-ok').textContent = `${state.ok.length}`;
  document.getElementById('count-not').textContent = `${state.notOk.length}`;
}

async function moveItems(sourceListId, targetStatus) {
  const listEl = document.getElementById(sourceListId);
  const selected = Array.from(listEl.selectedOptions).map(opt => opt.value);
  if (!selected.length) return;
  await fetch('/api/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level: state.level, keys: selected, status: targetStatus })
  });
  await loadLists();
}

async function showEvidence(key) {
  if (!key) return;
  const params = new URLSearchParams({ level: state.level, key });
  const resp = await fetch(`/api/evidence?${params.toString()}`);
  const data = await resp.json();
  const evidence = document.getElementById('evidence-body');
  if (data.error) {
    evidence.innerHTML = `<div class="meta">${data.error}</div>`;
    return;
  }
  const lines = [];
  if (data.artist) lines.push(`<div><strong>Artist:</strong> ${data.artist}</div>`);
  if (data.album) lines.push(`<div><strong>Album:</strong> ${data.album}</div>`);
  if (data.title) lines.push(`<div><strong>Title:</strong> ${data.title}</div>`);
  if (data.genre) lines.push(`<div><strong>Genre:</strong> ${data.genre}</div>`);
  if (data.bpm) lines.push(`<div><strong>BPM:</strong> ${data.bpm}</div>`);
  if (data.key) lines.push(`<div><strong>Key:</strong> ${data.key}</div>`);
  if (data.energy) lines.push(`<div><strong>Energy:</strong> ${data.energy}</div>`);
  if (data.danceability) lines.push(`<div><strong>Danceability:</strong> ${data.danceability}</div>`);
  if (data.duration) lines.push(`<div><strong>Duration:</strong> ${data.duration.toFixed(1)}s</div>`);
  if (data.duration_status) lines.push(`<div><strong>Duration Status:</strong> ${data.duration_status}</div>`);
  if (data.download_source) lines.push(`<div><strong>Source:</strong> ${data.download_source}</div>`);
  if (data.track_count) lines.push(`<div><strong>Tracks:</strong> ${data.track_count}</div>`);
  if (data.path) lines.push(`<div><strong>Path:</strong> ${data.path}</div>`);

  let autoHtml = '';
  if (data.auto) {
    const verdict = data.auto.verdict || 'review';
    const score = (data.auto.score === null || data.auto.score === undefined) ? '' : ` (score ${data.auto.score})`;
    const reasons = (data.auto.reasons || []).map(r => `<div class="meta">• ${r}</div>`).join('');
    autoHtml = `
      <h3>Auto Verdict</h3>
      <div class="meta"><strong>${verdict.toUpperCase()}</strong>${score}</div>
      ${reasons || '<div class="meta">No reasons</div>'}
    `;
  }

  let linksHtml = '';
  if (data.links && data.links.length) {
    linksHtml = '<div class="links">' + data.links.map(link => {
      return `<a href="${link.url}" target="_blank" rel="noreferrer">${link.label}</a>`;
    }).join('') + '</div>';
  }

  evidence.innerHTML = `
    <h3>Details</h3>
    <div class="meta">${lines.join('')}</div>
    ${autoHtml}
    <h3>Web Reviews</h3>
    ${linksHtml || '<div class="meta">No links</div>'}
  `;
}

async function exportUsb() {
  const statusEl = document.getElementById('export-status');
  const button = document.getElementById('export-usb');
  const payload = {
    usb_path: document.getElementById('export-usb-path').value.trim(),
    policy_path: document.getElementById('export-policy-path').value.trim(),
    jobs: Number(document.getElementById('export-jobs').value || 4),
    artwork_max_kb: Number(document.getElementById('export-artwork').value || 0),
    overwrite: document.getElementById('export-overwrite').checked,
    pioneer_finalize: document.getElementById('export-finalize').checked,
    rekordbox_xml: document.getElementById('export-rekordbox').value.trim(),
  };
  statusEl.textContent = 'Running export...';
  button.disabled = true;
  try {
    const resp = await fetch('/api/export_usb', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await resp.json();
    if (!resp.ok) {
      statusEl.textContent = data.error || 'Export failed';
      return;
    }
    const lines = [
      `Exit: ${data.exit_code}`,
      `M3U: ${data.m3u} (${data.count} tracks)`
    ];
    if (data.stdout) {
      lines.push('--- STDOUT ---');
      lines.push(data.stdout.trim());
    }
    if (data.stderr) {
      lines.push('--- STDERR ---');
      lines.push(data.stderr.trim());
    }
    statusEl.textContent = lines.join('\\n');
  } catch (err) {
    statusEl.textContent = `Export error: ${err}`;
  } finally {
    button.disabled = false;
  }
}

function bindListEvidence(listId) {
  const listEl = document.getElementById(listId);
  listEl.addEventListener('change', () => {
    const selected = listEl.selectedOptions[0];
    if (selected) {
      showEvidence(selected.value);
    }
  });
}

function bindTabs() {
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', async () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.level = btn.dataset.level;
      toggleFilters();
      await loadLists();
    });
  });
}

function getFilters() {
  return {
    auto: document.getElementById('filter-auto').value.trim(),
    genre: document.getElementById('filter-genre').value.trim(),
    source: document.getElementById('filter-source').value.trim(),
    bpmMin: document.getElementById('filter-bpm-min').value.trim(),
    bpmMax: document.getElementById('filter-bpm-max').value.trim(),
    durMin: document.getElementById('filter-dur-min').value.trim(),
    durMax: document.getElementById('filter-dur-max').value.trim(),
    mismatch: document.getElementById('filter-mismatch').checked,
  };
}

function bindFilters() {
  const panel = document.getElementById('track-filters');
  panel.querySelectorAll('input, select').forEach(el => {
    el.addEventListener('input', loadLists);
    el.addEventListener('change', loadLists);
  });
}

function toggleFilters() {
  const panel = document.getElementById('track-filters');
  panel.style.display = state.level === 'track' ? 'grid' : 'none';
}

window.addEventListener('DOMContentLoaded', async () => {
  bindTabs();
  bindFilters();
  bindListEvidence('list-ok');
  bindListEvidence('list-not');
  document.getElementById('to-ok').addEventListener('click', () => moveItems('list-not', 'ok'));
  document.getElementById('to-not').addEventListener('click', () => moveItems('list-ok', 'not_ok'));
  document.getElementById('reload-ok').addEventListener('click', loadLists);
  document.getElementById('reload-not').addEventListener('click', loadLists);
  document.getElementById('export-usb').addEventListener('click', exportUsb);
  toggleFilters();
  await loadLists();
});
</script>
</body>
</html>
"""


def inject_context() -> dict[str, Any]:
    try:
        db_path = str(_resolve_db_path())
    except Exception:
        db_path = "unresolved"
    default_policy = os.environ.get("DJ_REVIEW_POLICY") or str(_resolve_policy_path(None))
    return {
        "db_path": db_path,
        "default_usb": os.environ.get(
            "DJ_REVIEW_USB_PATH",
            os.environ.get("DJ_USB_ROOT", ""),
        ),
        "default_policy": default_policy,
        "default_jobs": os.environ.get("DJ_REVIEW_JOBS", "4"),
        "default_artwork": os.environ.get("DJ_REVIEW_ARTWORK_MAX_KB", "500"),
        "default_rekordbox": os.environ.get("DJ_REVIEW_REKORDBOX_XML", "rekordbox.xml"),
    }


APP.add_url_rule("/", view_func=index)
APP.add_url_rule("/api/items", view_func=items)
APP.add_url_rule("/api/move", view_func=move, methods=["POST"])
APP.add_url_rule("/api/evidence", view_func=evidence)
APP.add_url_rule("/api/export", view_func=export, methods=["POST"])
APP.add_url_rule("/api/export_usb", view_func=export_usb, methods=["POST"])
APP.context_processor(inject_context)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tagslut DJ review web app")
    parser.add_argument("--db", dest="db_path", default=None, help="Path to SQLite DB")
    parser.add_argument("--library-prefix", default=None, help="Filter files by path prefix")
    parser.add_argument("--host", default=os.environ.get("DJ_REVIEW_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DJ_REVIEW_PORT", "5055")))
    parser.add_argument("--no-open", action="store_true", help="Do not open browser on launch")
    return parser.parse_args()


def run_review_app(
    *,
    db: str | None = None,
    port: int = 5055,
    host: str = "127.0.0.1",
    open_browser: bool = True,
    library_prefix: str | None = None,
) -> None:
    """Run the DJ review Flask app with explicit runtime options."""
    if db:
        APP.config["DB_PATH"] = db
    if library_prefix:
        APP.config["LIBRARY_PREFIX"] = library_prefix

    if open_browser:
        open_host = host
        if open_host in {"0.0.0.0", "::"}:
            open_host = "127.0.0.1"
        url = f"http://{open_host}:{int(port)}"
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    APP.run(host=host, port=int(port), debug=False, use_reloader=False)


def main() -> None:
    args = _parse_args()
    run_review_app(
        db=args.db_path,
        library_prefix=args.library_prefix,
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
    )


if __name__ == "__main__":
    main()
