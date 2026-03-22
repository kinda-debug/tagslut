#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExistingHit:
    path: str
    canonical_artist: str | None
    canonical_title: str | None
    match_source: str


def _norm_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm_name(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip().lower()


def _norm_isrc(value: Any) -> str | None:
    text = _norm_text(value)
    if not text:
        return None
    return text.upper()


@lru_cache(maxsize=65536)
def _path_exists(path_text: str) -> bool:
    return Path(path_text).exists()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _expand_env_value(value: str, env_map: dict[str, str]) -> str:
    pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return env_map.get(key, os.environ.get(key, match.group(0)))

    return pattern.sub(repl, value)


def _discover_library_root(explicit_root: str | None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    for key in ("MASTER_LIBRARY", "LIBRARY_ROOT", "VOLUME_LIBRARY"):
        value = os.environ.get(key, "").strip()
        if value:
            return Path(value).expanduser().resolve()

    env_values = _load_env_file(_repo_root() / ".env")
    merged_env = {**env_values}
    for key, value in list(merged_env.items()):
        merged_env[key] = _expand_env_value(value, merged_env)
    for key in ("MASTER_LIBRARY", "LIBRARY_ROOT", "VOLUME_LIBRARY"):
        value = merged_env.get(key, "").strip()
        if value:
            return Path(value).expanduser().resolve()

    raise SystemExit("Could not resolve MASTER_LIBRARY. Pass --library-root or set MASTER_LIBRARY.")


def _is_usable_existing_path(path_text: str, library_root: Path) -> bool:
    if not _path_exists(path_text):
        return False
    candidate = Path(path_text).expanduser().resolve()
    if not _is_relative_to(candidate, library_root):
        return False
    return True


def _dedupe_hits(hits: list[ExistingHit]) -> list[ExistingHit]:
    seen: set[tuple[str, str]] = set()
    deduped: list[ExistingHit] = []
    for hit in sorted(hits, key=lambda item: (item.match_source, item.path)):
        key = (hit.match_source, hit.path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(hit)
    return deduped


def _load_existing_indexes(
    conn: sqlite3.Connection,
    library_root: Path,
) -> tuple[dict[str, list[ExistingHit]], dict[tuple[str, str], list[ExistingHit]]]:
    isrc_hits: dict[str, list[ExistingHit]] = defaultdict(list)
    name_hits: dict[tuple[str, str], list[ExistingHit]] = defaultdict(list)

    v3_rows = conn.execute(
        """
        SELECT
            COALESCE(canonical.isrc, ti.isrc) AS isrc,
            COALESCE(canonical.artist_norm, ti.artist_norm) AS artist_norm,
            COALESCE(canonical.title_norm, ti.title_norm) AS title_norm,
            COALESCE(canonical.canonical_artist, ti.canonical_artist) AS canonical_artist,
            COALESCE(canonical.canonical_title, ti.canonical_title) AS canonical_title,
            af.path AS path
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        JOIN track_identity ti ON ti.id = al.identity_id
        LEFT JOIN track_identity canonical ON canonical.id = ti.merged_into_id
        WHERE al.active = 1
          AND af.path IS NOT NULL
          AND TRIM(af.path) <> ''
        """
    ).fetchall()

    for row in v3_rows:
        path_text = _norm_text(row["path"])
        if not path_text or not _is_usable_existing_path(path_text, library_root):
            continue
        hit = ExistingHit(
            path=path_text,
            canonical_artist=_norm_text(row["canonical_artist"]),
            canonical_title=_norm_text(row["canonical_title"]),
            match_source="v3",
        )
        isrc = _norm_isrc(row["isrc"])
        if isrc:
            isrc_hits[isrc].append(hit)
        artist_key = _norm_name(row["artist_norm"] or row["canonical_artist"])
        title_key = _norm_name(row["title_norm"] or row["canonical_title"])
        if artist_key and title_key:
            name_hits[(artist_key, title_key)].append(hit)

    if _table_exists(conn, "files"):
        legacy_rows = conn.execute(
            """
            SELECT
                canonical_isrc AS isrc,
                canonical_artist,
                canonical_title,
                path
            FROM files
            WHERE canonical_isrc IS NOT NULL
              AND TRIM(canonical_isrc) <> ''
              AND path IS NOT NULL
              AND TRIM(path) <> ''
            """
        ).fetchall()

        for row in legacy_rows:
            path_text = _norm_text(row["path"])
            if not path_text or not _is_usable_existing_path(path_text, library_root):
                continue
            hit = ExistingHit(
                path=path_text,
                canonical_artist=_norm_text(row["canonical_artist"]),
                canonical_title=_norm_text(row["canonical_title"]),
                match_source="legacy_files",
            )
            isrc = _norm_isrc(row["isrc"])
            if isrc:
                isrc_hits[isrc].append(hit)
            artist_key = _norm_name(row["canonical_artist"])
            title_key = _norm_name(row["canonical_title"])
            if artist_key and title_key:
                name_hits[(artist_key, title_key)].append(hit)

    deduped_isrc_hits = {key: _dedupe_hits(value) for key, value in isrc_hits.items()}
    deduped_name_hits = {key: _dedupe_hits(value) for key, value in name_hits.items()}
    return deduped_isrc_hits, deduped_name_hits


def _find_existing_hit(
    track: dict[str, Any],
    isrc_hits: dict[str, list[ExistingHit]],
    name_hits: dict[tuple[str, str], list[ExistingHit]],
) -> tuple[str, ExistingHit] | None:
    isrc = _norm_isrc(track.get("isrc"))
    if isrc and isrc in isrc_hits:
        return "isrc", isrc_hits[isrc][0]
    if isrc:
        return None

    artist_key = _norm_name(track.get("artist"))
    title_key = _norm_name(track.get("track"))
    if artist_key and title_key:
        key = (artist_key, title_key)
        if key in name_hits:
            return "artist_title_exact", name_hits[key][0]
    return None


def _default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.without-existing.json")


def _default_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.report.json")


def prune_songshift_json(
    playlists: list[dict[str, Any]],
    isrc_hits: dict[str, list[ExistingHit]],
    name_hits: dict[tuple[str, str], list[ExistingHit]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    revised: list[dict[str, Any]] = []
    removed_tracks: list[dict[str, Any]] = []
    removed_by_method: dict[str, int] = defaultdict(int)
    total_tracks = 0

    for playlist in playlists:
        tracks = playlist.get("tracks")
        if not isinstance(tracks, list):
            raise ValueError(f"playlist {playlist.get('name')!r} has non-list 'tracks'")

        kept_tracks: list[dict[str, Any]] = []
        for track in tracks:
            if not isinstance(track, dict):
                raise ValueError(f"playlist {playlist.get('name')!r} contains non-object track entries")
            total_tracks += 1
            match = _find_existing_hit(track, isrc_hits, name_hits)
            if match is None:
                kept_tracks.append(track)
                continue

            method, hit = match
            removed_by_method[method] += 1
            removed_tracks.append(
                {
                    "playlist": _norm_text(playlist.get("name")),
                    "artist": _norm_text(track.get("artist")),
                    "track": _norm_text(track.get("track")),
                    "album": _norm_text(track.get("album")),
                    "isrc": _norm_isrc(track.get("isrc")),
                    "match_method": method,
                    "matched_path": hit.path,
                    "matched_artist": hit.canonical_artist,
                    "matched_title": hit.canonical_title,
                    "match_source": hit.match_source,
                }
            )

        playlist_copy = dict(playlist)
        playlist_copy["tracks"] = kept_tracks
        revised.append(playlist_copy)

    kept_total = sum(len(playlist["tracks"]) for playlist in revised)
    removed_total = len(removed_tracks)
    summary = {
        "playlists_total": len(playlists),
        "tracks_total": total_tracks,
        "removed_total": removed_total,
        "kept_total": kept_total,
        "removed_by_method": dict(sorted(removed_by_method.items())),
        "removed_tracks": removed_tracks,
    }
    return revised, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prune SongShift playlist JSON by removing tracks that already exist on disk."
    )
    parser.add_argument("--input", required=True, help="Path to SongShift JSON export.")
    parser.add_argument("--db", required=True, help="Path to the tagslut SQLite database.")
    parser.add_argument(
        "--library-root",
        help="MASTER_LIBRARY root to treat as existing FLAC inventory. Defaults to MASTER_LIBRARY/LIBRARY_ROOT/VOLUME_LIBRARY or repo .env.",
    )
    parser.add_argument("--output", help="Output path for the revised JSON.")
    parser.add_argument("--report-output", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"input JSON not found: {input_path}")
    if not db_path.exists():
        raise SystemExit(f"database not found: {db_path}")
    library_root = _discover_library_root(args.library_root)
    if not library_root.exists():
        raise SystemExit(f"library root not found: {library_root}")

    output_path = Path(args.output).expanduser().resolve() if args.output else _default_output_path(input_path)
    report_path = (
        Path(args.report_output).expanduser().resolve()
        if args.report_output
        else _default_report_path(output_path)
    )

    playlists = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(playlists, list):
        raise SystemExit("SongShift JSON must be a top-level list of playlists")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        isrc_hits, name_hits = _load_existing_indexes(conn, library_root)
    finally:
        conn.close()

    revised, summary = prune_songshift_json(playlists, isrc_hits, name_hits)
    output_path.write_text(json.dumps(revised, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_payload = {
        "input": str(input_path),
        "db": str(db_path),
        "library_root": str(library_root),
        "output": str(output_path),
        **summary,
    }
    report_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"input: {input_path}")
    print(f"output: {output_path}")
    print(f"report: {report_path}")
    print(f"library_root: {library_root}")
    print(f"playlists_total: {summary['playlists_total']}")
    print(f"tracks_total: {summary['tracks_total']}")
    print(f"removed_total: {summary['removed_total']}")
    print(f"kept_total: {summary['kept_total']}")
    print(f"removed_by_method: {json.dumps(summary['removed_by_method'], sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
