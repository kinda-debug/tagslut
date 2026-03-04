#!/usr/bin/env python3
"""Export v3 DJ candidate identities to CSV (read-only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

REQUIRED_TABLES = ("track_identity", "asset_link", "asset_file")
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
WHERE_CLAUSE_RE = re.compile(r"\s+AND\s+", re.IGNORECASE)


class WherePredicateError(ValueError):
    """Raised when --where contains unsupported predicates."""


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


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _active_link_where(conn: sqlite3.Connection) -> str:
    if _column_exists(conn, "asset_link", "active"):
        return "al.active = 1"
    return "1=1"


def _column_expr(conn: sqlite3.Connection, table: str, alias: str, column: str, out_alias: str) -> str:
    if _column_exists(conn, table, column):
        return f"{alias}.{column} AS {out_alias}"
    return f"NULL AS {out_alias}"


def _parse_where_clause(fragment: str | None) -> list[tuple[str, str, object | None]]:
    if fragment is None or fragment.strip() == "":
        return []

    predicates: list[tuple[str, str, object | None]] = []
    for raw_clause in WHERE_CLAUSE_RE.split(fragment.strip()):
        clause = raw_clause.strip()
        if not clause:
            continue

        null_match = re.fullmatch(r"(isrc|beatport_id)\s+IS\s+(NOT\s+)?NULL", clause, flags=re.IGNORECASE)
        if null_match:
            field = null_match.group(1).lower()
            op = "is_not_null" if null_match.group(2) else "is_null"
            predicates.append((field, op, None))
            continue

        eq_text = re.fullmatch(r"(genre|sub_genre|artist|title)\s*=\s*'([^']*)'", clause, flags=re.IGNORECASE)
        if eq_text:
            predicates.append((eq_text.group(1).lower(), "=", eq_text.group(2)))
            continue

        cmp_num = re.fullmatch(
            r"(bpm|duration_s)\s*(>=|<=|=|>|<)\s*(-?\d+(?:\.\d+)?)",
            clause,
            flags=re.IGNORECASE,
        )
        if cmp_num:
            predicates.append((cmp_num.group(1).lower(), cmp_num.group(2), float(cmp_num.group(3))))
            continue

        raise WherePredicateError(
            "unsupported --where predicate; allowed: genre/sub_genre/artist/title equality, "
            "bpm/duration_s numeric comparisons, isrc/beatport_id NULL checks, joined by AND"
        )

    return predicates


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


def _passes_where_predicates(
    row: dict[str, object],
    predicates: list[tuple[str, str, object | None]],
    *,
    strict: bool,
) -> bool:
    for field, op, expected in predicates:
        value = row.get(field)
        if op == "is_null":
            if _text(value) != "":
                return False
            continue
        if op == "is_not_null":
            if _text(value) == "":
                return False
            continue
        if op == "=":
            if _text(value).casefold() != str(expected or "").casefold():
                return False
            continue
        if field in {"bpm", "duration_s"} and op in {">", ">=", "<", "<=", "="}:
            numeric = _to_float_or_none(value)
            if numeric is None:
                if strict:
                    return False
                continue
            expected_num = float(expected) if expected is not None else 0.0
            if op == ">" and not (numeric > expected_num):
                return False
            if op == ">=" and not (numeric >= expected_num):
                return False
            if op == "<" and not (numeric < expected_num):
                return False
            if op == "<=" and not (numeric <= expected_num):
                return False
            if op == "=" and not (numeric == expected_num):
                return False
            continue
        return False
    return True


def _build_rows(
    conn: sqlite3.Connection,
    *,
    include_orphans: bool,
    require_preferred: bool,
    min_bpm: float | None,
    max_bpm: float | None,
    min_duration: float | None,
    max_duration: float | None,
    where_predicates: list[tuple[str, str, object | None]],
    strict: bool,
) -> tuple[list[dict[str, object]], dict[str, int]]:
    has_status = _table_exists(conn, "identity_status")
    has_preferred = _table_exists(conn, "preferred_asset")
    has_merged = _column_exists(conn, "track_identity", "merged_into_id")

    active_link_where = _active_link_where(conn)
    merged_where = "ti.merged_into_id IS NULL" if has_merged else "1=1"
    status_join = "LEFT JOIN identity_status ist ON ist.identity_id = ti.id" if has_status else ""
    status_select = "ist.status AS status" if has_status else "'unknown' AS status"

    preferred_join = ""
    preferred_cols = {
        "preferred_asset_id": "NULL AS preferred_asset_id",
        "preferred_path": "NULL AS preferred_path",
        "preferred_sample_rate": "NULL AS preferred_sample_rate",
        "preferred_bit_depth": "NULL AS preferred_bit_depth",
        "preferred_integrity_state": "NULL AS preferred_integrity_state",
        "preferred_duration_s": "NULL AS preferred_duration_s",
        "preferred_bpm": "NULL AS preferred_bpm",
        "preferred_key": "NULL AS preferred_key",
        "preferred_genre": "NULL AS preferred_genre",
    }
    if has_preferred:
        preferred_join = """
        LEFT JOIN preferred_asset pa ON pa.identity_id = ti.id
        LEFT JOIN asset_file paf ON paf.id = pa.asset_id
        """
        preferred_cols = {
            "preferred_asset_id": "pa.asset_id AS preferred_asset_id",
            "preferred_path": "paf.path AS preferred_path",
            "preferred_sample_rate": "paf.sample_rate AS preferred_sample_rate",
            "preferred_bit_depth": "paf.bit_depth AS preferred_bit_depth",
            "preferred_integrity_state": "paf.integrity_state AS preferred_integrity_state",
            "preferred_duration_s": "paf.duration_s AS preferred_duration_s",
            "preferred_bpm": _column_expr(conn, "asset_file", "paf", "bpm", "preferred_bpm"),
            "preferred_key": _column_expr(conn, "asset_file", "paf", "key_camelot", "preferred_key"),
            "preferred_genre": _column_expr(conn, "asset_file", "paf", "genre", "preferred_genre"),
        }

    canonical_album_expr = _column_expr(conn, "track_identity", "ti", "canonical_album", "canonical_album")

    status_filter = ""
    params: list[object] = []
    if has_status:
        allowed = ("active", "orphan") if include_orphans else ("active",)
        placeholders = ",".join("?" for _ in allowed)
        status_filter = f"AND COALESCE(ist.status, 'unknown') IN ({placeholders})"
        params.extend(allowed)
    elif not include_orphans:
        status_filter = "AND COALESCE(ast.asset_count, 0) > 0"

    rows = conn.execute(
        f"""
        WITH asset_stats AS (
            SELECT
                al.identity_id AS identity_id,
                COUNT(*) AS asset_count,
                MIN(af.duration_s) AS any_duration_s
            FROM asset_link al
            JOIN asset_file af ON af.id = al.asset_id
            WHERE {active_link_where}
            GROUP BY al.identity_id
        )
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            {canonical_album_expr},
            ti.isrc AS isrc,
            ti.beatport_id AS beatport_id,
            ti.canonical_bpm AS canonical_bpm,
            ti.canonical_key AS canonical_key,
            ti.canonical_genre AS canonical_genre,
            ti.canonical_sub_genre AS canonical_sub_genre,
            ti.canonical_duration AS canonical_duration,
            ti.enriched_at AS enriched_at,
            {status_select},
            COALESCE(ast.asset_count, 0) AS asset_count,
            ast.any_duration_s AS any_duration_s,
            {preferred_cols['preferred_asset_id']},
            {preferred_cols['preferred_path']},
            {preferred_cols['preferred_sample_rate']},
            {preferred_cols['preferred_bit_depth']},
            {preferred_cols['preferred_integrity_state']},
            {preferred_cols['preferred_duration_s']},
            {preferred_cols['preferred_bpm']},
            {preferred_cols['preferred_key']},
            {preferred_cols['preferred_genre']}
        FROM track_identity ti
        LEFT JOIN asset_stats ast ON ast.identity_id = ti.id
        {status_join}
        {preferred_join}
        WHERE {merged_where}
        {status_filter}
        ORDER BY ti.id ASC
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
        if require_preferred and preferred_asset_id is None:
            stats["excluded_no_preferred"] += 1
            continue

        bpm_value = _to_float_or_none(row["canonical_bpm"])
        if bpm_value is None:
            bpm_value = _to_float_or_none(row["preferred_bpm"])

        duration_value = _to_float_or_none(row["canonical_duration"])
        if duration_value is None:
            duration_value = _to_float_or_none(row["preferred_duration_s"])
        if duration_value is None:
            duration_value = _to_float_or_none(row["any_duration_s"])

        key_value = _text(row["canonical_key"]) or _text(row["preferred_key"])
        genre_value = _text(row["canonical_genre"]) or _text(row["preferred_genre"])
        artist = _text(row["artist"])
        title = _text(row["title"])

        candidate = {
            "identity_id": int(row["identity_id"]),
            "identity_key": _text(row["identity_key"]),
            "artist": artist,
            "title": title,
            "album": _text(row["canonical_album"]),
            "isrc": _text(row["isrc"]),
            "beatport_id": _text(row["beatport_id"]),
            "bpm": bpm_value,
            "key": key_value,
            "genre": genre_value,
            "sub_genre": _text(row["canonical_sub_genre"]),
            "duration_s": duration_value,
            "preferred_asset_id": int(preferred_asset_id) if preferred_asset_id is not None else "",
            "preferred_path": _text(row["preferred_path"]),
            "sample_rate": row["preferred_sample_rate"] if row["preferred_sample_rate"] is not None else "",
            "bit_depth": row["preferred_bit_depth"] if row["preferred_bit_depth"] is not None else "",
            "integrity_state": _text(row["preferred_integrity_state"]),
            "enriched_at": _text(row["enriched_at"]),
            "status": _text(row["status"]) or "unknown",
        }

        if not _passes_numeric_bounds(value=bpm_value, min_value=min_bpm, max_value=max_bpm, strict=strict):
            stats["excluded_by_filters"] += 1
            continue
        if not _passes_numeric_bounds(value=duration_value, min_value=min_duration, max_value=max_duration, strict=strict):
            stats["excluded_by_filters"] += 1
            continue
        if not _passes_where_predicates(candidate, where_predicates, strict=strict):
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
    parser.add_argument("--where", help="Optional allowlisted identity filter predicates joined by AND")
    parser.add_argument("--limit", type=int, help="Optional row limit for exported CSV")
    parser.add_argument("--include-orphans", action="store_true", help="Include orphan identities")
    parser.add_argument(
        "--require-preferred",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require preferred_asset row (default: true)",
    )
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

    try:
        where_predicates = _parse_where_clause(args.where)
    except WherePredicateError as exc:
        print(f"invalid --where: {exc}")
        return 2

    try:
        conn = _connect_ro(args.db)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    try:
        for table in REQUIRED_TABLES:
            if not _table_exists(conn, table):
                print(f"missing required table: {table}")
                return 2

        has_preferred = _table_exists(conn, "preferred_asset")
        if bool(args.require_preferred) and not has_preferred:
            print("missing required table: preferred_asset (required by --require-preferred)")
            return 2

        rows, stats = _build_rows(
            conn,
            include_orphans=bool(args.include_orphans),
            require_preferred=bool(args.require_preferred),
            min_bpm=args.min_bpm,
            max_bpm=args.max_bpm,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            where_predicates=where_predicates,
            strict=bool(args.strict),
        )
    finally:
        conn.close()

    csv_path = _write_csv(args.out, rows, args.limit)

    print(f"v3 db: {args.db.expanduser().resolve()}")
    print(f"out: {csv_path}")
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
