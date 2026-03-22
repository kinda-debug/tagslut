#!/usr/bin/env python3
"""Export v3 DJ candidate identities to CSV (read-only)."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from tagslut.storage.v3.identity_service import resolve_active_identity

CSV_COLUMNS = [
    "identity_id",
    "identity_key",
    "canonical_artist",
    "canonical_title",
    "canonical_album",
    "isrc",
    "beatport_id",
    "tidal_id",
    "qobuz_id",
    "canonical_bpm",
    "canonical_key",
    "canonical_genre",
    "canonical_sub_genre",
    "canonical_year",
    "duration_s",
    "selected_asset_id",
    "selected_asset_path",
    "selected_asset_format",
    "selected_asset_bitrate",
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


def _to_int_or_none(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    raw = str(value).strip()
    if raw == "":
        return None
    try:
        return int(float(raw))
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


def _load_identity_rows(
    conn: sqlite3.Connection,
    *,
    scope: str,
    min_rating: int | None,
    min_energy: int | None,
    only_profiled: bool,
    genres: list[str],
    keys: list[str],
) -> list[sqlite3.Row]:
    where: list[str] = ["ti.merged_into_id IS NULL"]
    params: list[object] = []

    if scope == "active":
        where.append("COALESCE(ist.status, 'unknown') = 'active'")
    elif scope == "active+orphan":
        where.append("COALESCE(ist.status, 'unknown') IN ('active', 'orphan')")

    if only_profiled:
        where.append("dj.updated_at IS NOT NULL")
    if min_rating is not None:
        where.append("dj.rating >= ?")
        params.append(int(min_rating))
    if min_energy is not None:
        where.append("dj.energy >= ?")
        params.append(int(min_energy))

    clean_genres = _normalize_list(genres)
    if clean_genres:
        placeholders = ",".join("?" for _ in clean_genres)
        where.append(f"LOWER(COALESCE(ti.canonical_genre, '')) IN ({placeholders})")
        params.extend(clean_genres)

    clean_keys = _normalize_list(keys)
    if clean_keys:
        placeholders = ",".join("?" for _ in clean_keys)
        where.append(f"LOWER(COALESCE(ti.canonical_key, '')) IN ({placeholders})")
        params.extend(clean_keys)

    where_sql = "WHERE " + " AND ".join(where)
    return conn.execute(
        f"""
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.isrc AS isrc,
            ti.beatport_id AS beatport_id,
            ti.tidal_id AS tidal_id,
            ti.qobuz_id AS qobuz_id,
            ti.canonical_artist AS canonical_artist,
            ti.canonical_title AS canonical_title,
            ti.canonical_album AS canonical_album,
            ti.canonical_bpm AS canonical_bpm,
            ti.canonical_key AS canonical_key,
            ti.canonical_genre AS canonical_genre,
            ti.canonical_sub_genre AS canonical_sub_genre,
            ti.canonical_year AS canonical_year,
            ti.canonical_duration AS canonical_duration,
            ti.enriched_at AS identity_enriched_at,
            COALESCE(ist.status, 'unknown') AS identity_status
        FROM track_identity ti
        LEFT JOIN identity_status ist ON ist.identity_id = ti.id
        LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id
        {where_sql}
        ORDER BY
            LOWER(COALESCE(ti.canonical_artist, '')),
            LOWER(COALESCE(ti.canonical_title, '')),
            ti.id ASC
        """,
        tuple(params),
    ).fetchall()


def _path_format(path_value: object) -> str:
    path_text = _text(path_value)
    if path_text == "":
        return ""
    return Path(path_text).suffix.lower().lstrip(".")


def _select_best_fallback_asset(rows: list[sqlite3.Row]) -> sqlite3.Row | None:
    if not rows:
        return None

    def sort_key(row: sqlite3.Row) -> tuple[int, int, int, int, int]:
        fmt = _path_format(row["path"])
        bitrate = _to_int_or_none(row["bitrate"]) or 0
        sample_rate = _to_int_or_none(row["sample_rate"]) or 0
        bit_depth = _to_int_or_none(row["bit_depth"]) or 0
        if fmt == "flac":
            bucket = 0
        elif fmt == "mp3":
            bucket = 1
        else:
            bucket = 2
        return (
            bucket,
            -bitrate,
            -sample_rate,
            -bit_depth,
            int(row["asset_id"]),
        )

    return min(rows, key=sort_key)


def _load_selected_assets(
    conn: sqlite3.Connection,
    candidate_identity_ids: set[int],
) -> dict[int, sqlite3.Row]:
    if not candidate_identity_ids:
        return {}

    resolved_cache: dict[int, int] = {}

    def canonical_identity_id(raw_identity_id: int) -> int:
        cached = resolved_cache.get(raw_identity_id)
        if cached is not None:
            return cached
        row = resolve_active_identity(conn, raw_identity_id)
        identity_id = int(row["id"])
        resolved_cache[raw_identity_id] = identity_id
        return identity_id

    preferred_by_identity: dict[int, list[sqlite3.Row]] = {}
    preferred_rows = conn.execute(
        """
        SELECT
            pa.identity_id AS raw_identity_id,
            af.id AS asset_id,
            af.path AS path,
            af.bitrate AS bitrate,
            af.sample_rate AS sample_rate,
            af.bit_depth AS bit_depth,
            af.integrity_state AS integrity_state,
            af.duration_s AS duration_s
        FROM preferred_asset pa
        JOIN asset_file af ON af.id = pa.asset_id
        ORDER BY pa.identity_id ASC, af.id ASC
        """
    ).fetchall()
    for row in preferred_rows:
        active_identity_id = canonical_identity_id(int(row["raw_identity_id"]))
        if active_identity_id not in candidate_identity_ids:
            continue
        preferred_by_identity.setdefault(active_identity_id, []).append(row)

    asset_rows_by_identity: dict[int, list[sqlite3.Row]] = {}
    asset_rows = conn.execute(
        """
        SELECT
            al.identity_id AS raw_identity_id,
            af.id AS asset_id,
            af.path AS path,
            af.bitrate AS bitrate,
            af.sample_rate AS sample_rate,
            af.bit_depth AS bit_depth,
            af.integrity_state AS integrity_state,
            af.duration_s AS duration_s
        FROM asset_link al
        JOIN asset_file af ON af.id = al.asset_id
        WHERE al.active = 1
        ORDER BY al.identity_id ASC, af.id ASC
        """
    ).fetchall()
    for row in asset_rows:
        active_identity_id = canonical_identity_id(int(row["raw_identity_id"]))
        if active_identity_id not in candidate_identity_ids:
            continue
        asset_rows_by_identity.setdefault(active_identity_id, []).append(row)

    selected: dict[int, sqlite3.Row] = {}
    for identity_id in sorted(candidate_identity_ids):
        preferred_rows_for_identity = preferred_by_identity.get(identity_id, [])
        if preferred_rows_for_identity:
            selected[identity_id] = min(
                preferred_rows_for_identity,
                key=lambda row: (
                    0 if int(row["raw_identity_id"]) == identity_id else 1,
                    int(row["raw_identity_id"]),
                    int(row["asset_id"]),
                ),
            )
            continue

        fallback = _select_best_fallback_asset(asset_rows_by_identity.get(identity_id, []))
        if fallback is not None:
            selected[identity_id] = fallback
    return selected


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
    identity_rows = _load_identity_rows(
        conn,
        scope=scope,
        min_rating=min_rating,
        min_energy=min_energy,
        only_profiled=only_profiled,
        genres=genres,
        keys=keys,
    )
    selected_assets = _load_selected_assets(
        conn,
        {int(row["identity_id"]) for row in identity_rows},
    )

    stats = {
        "total_identities_considered": len(identity_rows),
        "exported_rows": 0,
        "excluded_no_preferred": 0,
        "excluded_by_filters": 0,
        "missing_bpm_count": 0,
        "missing_key_count": 0,
        "missing_genre_count": 0,
        "missing_core_fields_count": 0,
    }

    out_rows: list[dict[str, object]] = []
    for row in identity_rows:
        identity_id = int(row["identity_id"])
        selected_asset = selected_assets.get(identity_id)
        if selected_asset is None:
            stats["excluded_no_preferred"] += 1
            continue

        bpm_value = _to_float_or_none(row["canonical_bpm"])
        duration_value = _to_float_or_none(row["canonical_duration"])
        if duration_value is None:
            duration_value = _to_float_or_none(selected_asset["duration_s"])
        key_value = _text(row["canonical_key"])
        genre_value = _text(row["canonical_genre"])
        artist = _text(row["canonical_artist"])
        title = _text(row["canonical_title"])

        candidate = {
            "identity_id": identity_id,
            "identity_key": _text(row["identity_key"]),
            "canonical_artist": artist,
            "canonical_title": title,
            "canonical_album": _text(row["canonical_album"]),
            "isrc": _text(row["isrc"]),
            "beatport_id": _text(row["beatport_id"]),
            "tidal_id": _text(row["tidal_id"]),
            "qobuz_id": _text(row["qobuz_id"]),
            "canonical_bpm": bpm_value,
            "canonical_key": key_value,
            "canonical_genre": genre_value,
            "canonical_sub_genre": _text(row["canonical_sub_genre"]),
            "canonical_year": _to_int_or_none(row["canonical_year"]) or "",
            "duration_s": duration_value,
            "selected_asset_id": int(selected_asset["asset_id"]),
            "selected_asset_path": _text(selected_asset["path"]),
            "selected_asset_format": _path_format(selected_asset["path"]),
            "selected_asset_bitrate": _to_int_or_none(selected_asset["bitrate"]) or "",
            "sample_rate": (
                _to_int_or_none(selected_asset["sample_rate"])
                if selected_asset["sample_rate"] is not None
                else ""
            ),
            "bit_depth": (
                _to_int_or_none(selected_asset["bit_depth"])
                if selected_asset["bit_depth"] is not None
                else ""
            ),
            "integrity_state": _text(selected_asset["integrity_state"]),
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

    out_rows.sort(
        key=lambda item: (
            str(item["canonical_artist"]).casefold(),
            str(item["canonical_title"]).casefold(),
            int(item["identity_id"]),
        )
    )
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
                    "canonical_artist": row["canonical_artist"],
                    "canonical_title": row["canonical_title"],
                    "canonical_album": row["canonical_album"],
                    "isrc": row["isrc"],
                    "beatport_id": row["beatport_id"],
                    "tidal_id": row["tidal_id"],
                    "qobuz_id": row["qobuz_id"],
                    "canonical_bpm": "" if row["canonical_bpm"] is None else row["canonical_bpm"],
                    "canonical_key": row["canonical_key"],
                    "canonical_genre": row["canonical_genre"],
                    "canonical_sub_genre": row["canonical_sub_genre"],
                    "canonical_year": row["canonical_year"],
                    "duration_s": "" if row["duration_s"] is None else row["duration_s"],
                    "selected_asset_id": row["selected_asset_id"],
                    "selected_asset_path": row["selected_asset_path"],
                    "selected_asset_format": row["selected_asset_format"],
                    "selected_asset_bitrate": row["selected_asset_bitrate"],
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
            print('hint: run "make apply-v3-schema V3=<db>" to install missing views')
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
