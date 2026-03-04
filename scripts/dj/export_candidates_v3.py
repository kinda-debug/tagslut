#!/usr/bin/env python3
"""Export v3 DJ candidate identities to CSV (read-only)."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

CSV_COLUMNS = [
    "identity_id",
    "identity_key",
    "artist",
    "title",
    "album",
    "isrc",
    "beatport_id",
    "bpm",
    "key",
    "genre",
    "sub_genre",
    "duration_s",
    "preferred_asset_id",
    "preferred_path",
    "sample_rate",
    "bit_depth",
    "integrity_state",
    "enriched_at",
    "status",
    "flags_json",
]
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


def _resolve_scope(args: argparse.Namespace) -> str:
    if args.scope:
        return args.scope
    if not bool(args.require_preferred):
        return "all"
    if bool(args.include_orphans):
        return "active+orphan"
    return "active"


def _normalize_list(values: list[str]) -> list[str]:
    return [value.strip().casefold() for value in values if value.strip()]


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    raw = str(value).strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _passes_numeric_bounds(
    *,
    value: float | None,
    min_value: float | None,
    max_value: float | None,
    strict: bool,
) -> bool:
    if min_value is None and max_value is None:
        return True
    if value is None:
        return not strict
    if min_value is not None and value < min_value:
        return False
    if max_value is not None and value > max_value:
        return False
    return True


def _build_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    min_rating: int | None,
    min_energy: int | None,
    only_profiled: bool,
    genres: list[str],
    keys: list[str],
    min_bpm: float | None,
    max_bpm: float | None,
    min_duration: float | None,
    max_duration: float | None,
    strict: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    view_name = SCOPE_TO_VIEW[scope]
    where: list[str] = []
    params: list[object] = []

    if only_profiled:
        where.append("dj_updated_at IS NOT NULL")
    if min_rating is not None:
        where.append("dj_rating >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        where.append("dj_energy >= ?")
        params.append(int(min_energy))

    clean_genres = _normalize_list(genres)
    if clean_genres:
        placeholders = ",".join("?" for _ in clean_genres)
        where.append(f"LOWER(COALESCE(genre,'')) IN ({placeholders})")
        params.extend(clean_genres)

    clean_keys = _normalize_list(keys)
    if clean_keys:
        placeholders = ",".join("?" for _ in clean_keys)
        where.append(f"LOWER(COALESCE(musical_key,'')) IN ({placeholders})")
        params.extend(clean_keys)

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(where)

    rows = conn.execute(
        f"""
        SELECT
            identity_id,
            identity_key,
            artist,
            title,
            album,
            isrc,
            beatport_id,
            bpm,
            musical_key,
            genre,
            sub_genre,
            duration_s,
            preferred_asset_id,
            asset_path,
            sample_rate,
            bit_depth,
            integrity_state,
            identity_enriched_at,
            identity_status
        FROM {view_name}
        {where_sql}
        ORDER BY LOWER(COALESCE(artist, '')), LOWER(COALESCE(title, '')), identity_id ASC
        """,
        tuple(params),
    ).fetchall()

    stats = {
        "total_identities_considered": len(rows),
        "exported_rows": 0,
        "excluded_no_preferred": 0,
        "excluded_by_filters": 0,
        "missing_bpm_count": 0,
        "missing_key_count": 0,
        "missing_genre_count": 0,
        "missing_core_fields_count": 0,
    }

    out_rows: list[dict[str, object]] = []
    for row in rows:
        preferred_asset_id = row["preferred_asset_id"]
        bpm_value = _to_float_or_none(row["bpm"])
        duration_value = _to_float_or_none(row["duration_s"])
        key_value = _text(row["musical_key"])
        genre_value = _text(row["genre"])
        artist = _text(row["artist"])
        title = _text(row["title"])

        candidate = {
            "identity_id": int(row["identity_id"]),
            "identity_key": _text(row["identity_key"]),
            "artist": artist,
            "title": title,
            "album": _text(row["album"]),
            "isrc": _text(row["isrc"]),
            "beatport_id": _text(row["beatport_id"]),
            "bpm": bpm_value,
            "key": key_value,
            "genre": genre_value,
            "sub_genre": _text(row["sub_genre"]),
            "duration_s": duration_value,
            "preferred_asset_id": int(preferred_asset_id) if preferred_asset_id is not None else "",
            "preferred_path": _text(row["asset_path"]),
            "sample_rate": row["sample_rate"] if row["sample_rate"] is not None else "",
            "bit_depth": row["bit_depth"] if row["bit_depth"] is not None else "",
            "integrity_state": _text(row["integrity_state"]),
            "enriched_at": _text(row["identity_enriched_at"]),
            "status": _text(row["identity_status"]) or "unknown",
        }

        if not _passes_numeric_bounds(value=bpm_value, min_value=min_bpm, max_value=max_bpm, strict=strict):
            stats["excluded_by_filters"] += 1
            continue
        if not _passes_numeric_bounds(value=duration_value, min_value=min_duration, max_value=max_duration, strict=strict):
            stats["excluded_by_filters"] += 1
            continue

        flags = {
            "missing_bpm": bpm_value is None,
            "missing_key": key_value == "",
            "missing_genre": genre_value == "",
            "missing_core_fields": artist == "" or title == "",
            "duration_missing": duration_value is None,
        }
        candidate["flags_json"] = json.dumps(flags, sort_keys=True, separators=(",", ":"))

        stats["missing_bpm_count"] += int(flags["missing_bpm"])
        stats["missing_key_count"] += int(flags["missing_key"])
        stats["missing_genre_count"] += int(flags["missing_genre"])
        stats["missing_core_fields_count"] += int(flags["missing_core_fields"])
        out_rows.append(candidate)

    out_rows.sort(key=lambda item: (str(item["artist"]).casefold(), str(item["title"]).casefold(), int(item["identity_id"])))
    stats["exported_rows"] = len(out_rows)
    return out_rows, stats


def _write_csv(path: Path, rows: list[dict[str, object]], limit: int | None) -> Path:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    rows_to_write = rows if limit is None else rows[: int(limit)]
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows_to_write:
            writer.writerow(
                {
                    "identity_id": row["identity_id"],
                    "identity_key": row["identity_key"],
                    "artist": row["artist"],
                    "title": row["title"],
                    "album": row["album"],
                    "isrc": row["isrc"],
                    "beatport_id": row["beatport_id"],
                    "bpm": "" if row["bpm"] is None else row["bpm"],
                    "key": row["key"],
                    "genre": row["genre"],
                    "sub_genre": row["sub_genre"],
                    "duration_s": "" if row["duration_s"] is None else row["duration_s"],
                    "preferred_asset_id": row["preferred_asset_id"],
                    "preferred_path": row["preferred_path"],
                    "sample_rate": row["sample_rate"],
                    "bit_depth": row["bit_depth"],
                    "integrity_state": row["integrity_state"],
                    "enriched_at": row["enriched_at"],
                    "status": row["status"],
                    "flags_json": row["flags_json"],
                }
            )
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export DJ candidates from v3 DB")
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path")
    parser.add_argument(
        "--scope",
        choices=tuple(SCOPE_TO_VIEW.keys()),
        help="Policy view scope (default: active)",
    )
    parser.add_argument("--limit", type=int, help="Optional row limit for exported CSV")
    parser.add_argument(
        "--include-orphans",
        action="store_true",
        help="Deprecated: use --scope active+orphan",
    )
    parser.add_argument(
        "--require-preferred",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Deprecated: use --scope all to include identities without preferred assets",
    )
    parser.add_argument("--only-profiled", action="store_true")
    parser.add_argument("--min-rating", type=int)
    parser.add_argument("--min-energy", type=int)
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--key", action="append", default=[])
    parser.add_argument("--min-bpm", type=float)
    parser.add_argument("--max-bpm", type=float)
    parser.add_argument("--min-duration", type=float, help="Minimum duration in seconds")
    parser.add_argument("--max-duration", type=float, help="Maximum duration in seconds")
    parser.add_argument("--format", choices=["csv"], default="csv")
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Strict filtering for missing numeric fields (default: true)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit is not None and int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2
    scope = _resolve_scope(args)
    view_name = SCOPE_TO_VIEW[scope]

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        if not _view_exists(conn, view_name):
            print(f"missing required view: {view_name}")
            return 2

        rows, stats = _build_rows(
            conn,
            scope=scope,
            min_rating=args.min_rating,
            min_energy=args.min_energy,
            only_profiled=bool(args.only_profiled),
            genres=args.genre,
            keys=args.key,
            min_bpm=args.min_bpm,
            max_bpm=args.max_bpm,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            strict=bool(args.strict),
        )
    finally:
        conn.close()

    csv_path = _write_csv(args.out, rows, args.limit)

    print(f"v3 db: {args.db.expanduser().resolve()}")
    print(f"out: {csv_path}")
    print(f"scope: {scope}")
    print(f"view: {view_name}")
    print(f"total_identities_considered: {stats['total_identities_considered']}")
    print(f"exported_rows: {stats['exported_rows'] if args.limit is None else min(stats['exported_rows'], int(args.limit))}")
    print(f"excluded_no_preferred: {stats['excluded_no_preferred']}")
    print(f"excluded_by_filters: {stats['excluded_by_filters']}")
    print(f"missing_bpm_count: {stats['missing_bpm_count']}")
    print(f"missing_key_count: {stats['missing_key_count']}")
    print(f"missing_genre_count: {stats['missing_genre_count']}")
    print(f"missing_core_fields_count: {stats['missing_core_fields_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
