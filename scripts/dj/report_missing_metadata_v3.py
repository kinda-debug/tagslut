#!/usr/bin/env python3
"""Report DJ candidates missing key metadata fields (read-only)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from urllib.parse import quote

CSV_COLUMNS = [
    "identity_id",
    "identity_status",
    "preferred_asset_id",
    "preferred_asset_path",
    "canonical_artist",
    "canonical_title",
    "isrc",
    "beatport_id",
    "traxsource_id",
    "spotify_id",
    "tidal_id",
    "deezer_id",
    "musicbrainz_id",
    "best_provider",
    "best_provider_id",
    "album",
    "bpm",
    "musical_key",
    "genre",
    "missing_bpm",
    "missing_key",
    "missing_genre",
    "missing_core_fields",
    "missing_strong_keys",
    "most_missing_fields",
    "dj_rating",
    "dj_energy",
    "dj_set_role",
    "dj_tags_json",
]

PROVIDER_LADDER = ("beatport", "traxsource", "spotify", "tidal", "deezer", "musicbrainz")

SCOPE_TO_VIEW = {
    "active": "v_dj_pool_candidates_active_v3",
    "active+orphan": "v_dj_pool_candidates_active_orphan_v3",
    "all": "v_dj_pool_candidates_v3",
}


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA query_only=ON")
    return conn


def _view_exists(conn: sqlite3.Connection, view: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name=?",
        (view,),
    ).fetchone()
    return row is not None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return resolved


def _build_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    min_rating: int | None,
    min_energy: int | None,
    only_profiled: bool,
    limit: int,
) -> list[dict[str, object]]:
    view_name = SCOPE_TO_VIEW[scope]
    has_dj_profile = _table_exists(conn, "dj_track_profile")

    dj_join = ""
    if has_dj_profile:
        dj_join = "LEFT JOIN dj_track_profile dj ON dj.identity_id = v.identity_id"
        dj_rating_expr = "COALESCE(v.dj_rating, dj.rating)"
        dj_energy_expr = "COALESCE(v.dj_energy, dj.energy)"
        dj_set_role_expr = "COALESCE(v.dj_set_role, dj.set_role)"
        dj_tags_expr = "COALESCE(v.dj_tags_json, dj.dj_tags_json)"
    else:
        dj_rating_expr = "v.dj_rating"
        dj_energy_expr = "v.dj_energy"
        dj_set_role_expr = "v.dj_set_role"
        dj_tags_expr = "v.dj_tags_json"

    missing_bpm_expr = "CASE WHEN v.bpm IS NULL THEN 1 ELSE 0 END"
    missing_key_expr = "CASE WHEN TRIM(COALESCE(v.musical_key,'')) = '' THEN 1 ELSE 0 END"
    missing_genre_expr = "CASE WHEN TRIM(COALESCE(v.genre,'')) = '' THEN 1 ELSE 0 END"
    missing_core_expr = (
        "CASE WHEN TRIM(COALESCE(v.artist,'')) = '' OR TRIM(COALESCE(v.title,'')) = '' THEN 1 ELSE 0 END"
    )
    most_missing_expr = (
        f"({missing_bpm_expr} + {missing_key_expr} + {missing_genre_expr} + {missing_core_expr})"
    )

    where: list[str] = []
    params: list[object] = []

    if only_profiled:
        where.append("v.dj_updated_at IS NOT NULL")
    if min_rating is not None:
        where.append(f"{dj_rating_expr} >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        where.append(f"{dj_energy_expr} >= ?")
        params.append(int(min_energy))

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    query = f"""
        SELECT
            v.identity_id AS identity_id,
            COALESCE(v.identity_status, 'unknown') AS identity_status,
            v.preferred_asset_id AS preferred_asset_id,
            v.asset_path AS preferred_asset_path,
            v.artist AS canonical_artist,
            v.title AS canonical_title,
            v.isrc AS isrc,
            v.beatport_id AS beatport_id,
            v.traxsource_id AS traxsource_id,
            v.spotify_id AS spotify_id,
            v.tidal_id AS tidal_id,
            v.deezer_id AS deezer_id,
            v.musicbrainz_id AS musicbrainz_id,
            v.album AS album,
            v.bpm AS bpm,
            v.musical_key AS musical_key,
            v.genre AS genre,
            {missing_bpm_expr} AS missing_bpm,
            {missing_key_expr} AS missing_key,
            {missing_genre_expr} AS missing_genre,
            {missing_core_expr} AS missing_core_fields,
            {most_missing_expr} AS most_missing_fields,
            {dj_rating_expr} AS dj_rating,
            {dj_energy_expr} AS dj_energy,
            {dj_set_role_expr} AS dj_set_role,
            {dj_tags_expr} AS dj_tags_json
        FROM {view_name} v
        {dj_join}
        {where_sql}
        ORDER BY
            most_missing_fields DESC,
            LOWER(COALESCE(v.artist, '')) ASC,
            LOWER(COALESCE(v.title, '')) ASC,
            v.identity_id ASC
        LIMIT ?
    """

    rows = conn.execute(query, tuple(params) + (int(limit),)).fetchall()
    out: list[dict[str, object]] = []
    for row in rows:
        isrc = _text(row["isrc"])
        provider_ids = {
            "beatport": _text(row["beatport_id"]),
            "traxsource": _text(row["traxsource_id"]),
            "spotify": _text(row["spotify_id"]),
            "tidal": _text(row["tidal_id"]),
            "deezer": _text(row["deezer_id"]),
            "musicbrainz": _text(row["musicbrainz_id"]),
        }
        missing_strong_keys = int(isrc == "" and all(provider_ids[name] == "" for name in PROVIDER_LADDER))
        best_provider = "none"
        best_provider_id = ""
        for provider_name in PROVIDER_LADDER:
            provider_id = provider_ids[provider_name]
            if provider_id:
                best_provider = provider_name
                best_provider_id = provider_id
                break
        out.append(
            {
                "identity_id": int(row["identity_id"]),
                "identity_status": _text(row["identity_status"]) or "unknown",
                "preferred_asset_id": "" if row["preferred_asset_id"] is None else int(row["preferred_asset_id"]),
                "preferred_asset_path": _text(row["preferred_asset_path"]),
                "canonical_artist": _text(row["canonical_artist"]),
                "canonical_title": _text(row["canonical_title"]),
                "isrc": isrc,
                "beatport_id": provider_ids["beatport"],
                "traxsource_id": provider_ids["traxsource"],
                "spotify_id": provider_ids["spotify"],
                "tidal_id": provider_ids["tidal"],
                "deezer_id": provider_ids["deezer"],
                "musicbrainz_id": provider_ids["musicbrainz"],
                "best_provider": best_provider,
                "best_provider_id": best_provider_id,
                "album": _text(row["album"]),
                "bpm": "" if row["bpm"] is None else row["bpm"],
                "musical_key": _text(row["musical_key"]),
                "genre": _text(row["genre"]),
                "missing_bpm": int(row["missing_bpm"]),
                "missing_key": int(row["missing_key"]),
                "missing_genre": int(row["missing_genre"]),
                "missing_core_fields": int(row["missing_core_fields"]),
                "missing_strong_keys": missing_strong_keys,
                "most_missing_fields": int(row["most_missing_fields"]),
                "dj_rating": "" if row["dj_rating"] is None else row["dj_rating"],
                "dj_energy": "" if row["dj_energy"] is None else row["dj_energy"],
                "dj_set_role": _text(row["dj_set_role"]),
                "dj_tags_json": _text(row["dj_tags_json"]) or "[]",
            }
        )
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report missing DJ metadata from v3 DB (includes Deezer IDs)"
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument("--out", type=Path, help="Optional output CSV path")
    parser.add_argument(
        "--scope",
        choices=tuple(SCOPE_TO_VIEW.keys()),
        default="active",
    )
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--only-profiled", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2

    scope = args.scope
    view_name = SCOPE_TO_VIEW[scope]

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        if not _view_exists(conn, view_name):
            print(f"missing required view: {view_name}")
            print('hint: run "make apply-v3-schema V3=<db>" to install missing views')
            return 2

        rows = _build_rows(
            conn,
            scope=scope,
            min_rating=args.min_rating,
            min_energy=args.min_energy,
            only_profiled=bool(args.only_profiled),
            limit=int(args.limit),
        )
    finally:
        conn.close()

    out_path: Path | None = None
    if args.out is not None:
        out_path = _write_csv(args.out, rows)

    missing_bpm_count = sum(int(row["missing_bpm"]) for row in rows)
    missing_key_count = sum(int(row["missing_key"]) for row in rows)
    missing_genre_count = sum(int(row["missing_genre"]) for row in rows)
    missing_core_count = sum(int(row["missing_core_fields"]) for row in rows)

    print(f"v3 db: {args.db.expanduser().resolve()}")
    print(f"scope: {scope}")
    print(f"view: {view_name}")
    print(f"rows: {len(rows)}")
    print(f"missing_bpm_count: {missing_bpm_count}")
    print(f"missing_key_count: {missing_key_count}")
    print(f"missing_genre_count: {missing_genre_count}")
    print(f"missing_core_fields_count: {missing_core_count}")
    if out_path is not None:
        print(f"out: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
