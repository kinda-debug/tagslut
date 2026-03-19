#!/usr/bin/env python3
"""Generate an identity QA report for a standalone v3 database."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from urllib.parse import quote

DEFAULT_LIMIT = 200
DURATION_SPREAD_THRESHOLD_MS = 2000
CSV_FIELDNAMES = [
    "identity_id",
    "identity_key",
    "isrc",
    "beatport_id",
    "canonical_artist",
    "canonical_title",
    "asset_count",
    "has_unidentified_key",
    "missing_core_fields",
    "mixed_quality",
    "duration_spread_ms",
]
REQUIRED_SCHEMA: dict[str, tuple[str, ...]] = {
    "track_identity": (
        "id",
        "identity_key",
        "isrc",
        "beatport_id",
        "tidal_id",
        # "qobuz_id",  # purged
        # "spotify_id",  # purged
        "canonical_artist",
        "canonical_title",
        "enriched_at",
    ),
    "asset_link": ("asset_id", "identity_id"),
    "asset_file": ("id", "duration_measured_ms", "sample_rate", "bit_depth"),
}


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {str(row[1]) for row in rows}


def _schema_errors(conn: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    for table, required_cols in REQUIRED_SCHEMA.items():
        columns = _get_columns(conn, table)
        if not columns:
            errors.append(f"missing table: {table}")
            continue
        missing = [col for col in required_cols if col not in columns]
        if missing:
            errors.append(f"missing columns in {table}: {', '.join(missing)}")
    return errors


def _is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _load_identity_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    has_merged_into = "merged_into_id" in _get_columns(conn, "track_identity")
    has_identity_status = _table_exists(conn, "identity_status")
    status_join = "LEFT JOIN identity_status ist ON ist.identity_id = ti.id" if has_identity_status else ""
    status_select = "ist.status AS status_row" if has_identity_status else "'' AS status_row"
    merged_select = "ti.merged_into_id AS merged_into_id" if has_merged_into else "NULL AS merged_into_id"

    rows = conn.execute(
        f"""
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.isrc AS isrc,
            ti.beatport_id AS beatport_id,
            ti.tidal_id AS tidal_id,
            # ti.qobuz_id AS qobuz_id,  # purged
            ti.spotify_id AS spotify_id,
            ti.canonical_artist AS canonical_artist,
            ti.canonical_title AS canonical_title,
            ti.enriched_at AS enriched_at,
            {status_select},
            {merged_select},
            COUNT(DISTINCT al.asset_id) AS asset_count,
            MIN(af.duration_measured_ms) AS min_duration_ms,
            MAX(af.duration_measured_ms) AS max_duration_ms,
            COUNT(
                DISTINCT CASE
                    WHEN af.sample_rate IS NULL THEN '__NULL__'
                    ELSE CAST(af.sample_rate AS TEXT)
                END
            ) AS sample_rate_variants,
            COUNT(
                DISTINCT CASE
                    WHEN af.bit_depth IS NULL THEN '__NULL__'
                    ELSE CAST(af.bit_depth AS TEXT)
                END
            ) AS bit_depth_variants
        FROM track_identity ti
        LEFT JOIN asset_link al ON al.identity_id = ti.id
        LEFT JOIN asset_file af ON af.id = al.asset_id
        {status_join}
        GROUP BY
            ti.id,
            ti.identity_key,
            ti.isrc,
            ti.beatport_id,
            ti.tidal_id,
            ti.qobuz_id,
            ti.spotify_id,
            ti.canonical_artist,
            ti.canonical_title,
            ti.enriched_at,
            status_row,
            merged_into_id
        ORDER BY ti.id ASC
        """
    ).fetchall()

    out: list[dict[str, object]] = []
    for row in rows:
        min_duration = row["min_duration_ms"]
        max_duration = row["max_duration_ms"]
        duration_spread_ms = 0
        if min_duration is not None and max_duration is not None:
            duration_spread_ms = int(max_duration) - int(min_duration)

        missing_core_fields = int(
            _is_blank(row["canonical_artist"]) or _is_blank(row["canonical_title"])
        )
        missing_strong_keys = int(
            _is_blank(row["isrc"])
            and _is_blank(row["beatport_id"])
            and _is_blank(row["tidal_id"])
            and _is_blank(row["qobuz_id"])
            and _is_blank(row["spotify_id"])
        )
        sample_rate_variants = int(row["sample_rate_variants"] or 0)
        bit_depth_variants = int(row["bit_depth_variants"] or 0)

        merged_into_raw = row["merged_into_id"]
        merged_into_id = int(merged_into_raw) if merged_into_raw is not None else None
        status_row = str(row["status_row"] or "").strip().lower()
        if merged_into_id is not None:
            lifecycle_status = "merged"
        elif status_row == "archived":
            lifecycle_status = "archived"
        elif status_row in {"active", "orphan"}:
            lifecycle_status = status_row
        else:
            lifecycle_status = "active" if int(row["asset_count"] or 0) > 0 else "orphan"

        out.append(
            {
                "identity_id": int(row["identity_id"]),
                "identity_key": str(row["identity_key"] or ""),
                "isrc": str(row["isrc"] or ""),
                "beatport_id": str(row["beatport_id"] or ""),
                "tidal_id": str(row["tidal_id"] or ""),
                "qobuz_id": str(row["qobuz_id"] or ""),
                "spotify_id": str(row["spotify_id"] or ""),
                "canonical_artist": str(row["canonical_artist"] or ""),
                "canonical_title": str(row["canonical_title"] or ""),
                "enriched_at": str(row["enriched_at"] or ""),
                "asset_count": int(row["asset_count"] or 0),
                "has_unidentified_key": int(
                    str(row["identity_key"] or "").startswith("unidentified:")
                ),
                "missing_core_fields": missing_core_fields,
                "missing_strong_keys": missing_strong_keys,
                "mixed_quality": int(
                    sample_rate_variants > 1 or bit_depth_variants > 1
                ),
                "duration_spread_ms": duration_spread_ms,
                "lifecycle_status": lifecycle_status,
            }
        )
    return out


def _load_duplicate_groups(
    conn: sqlite3.Connection, *, column: str, label: str, limit: int
) -> list[dict[str, object]]:
    norm_expr = f"TRIM({column})"
    if column == "isrc":
        norm_expr = f"UPPER(TRIM({column}))"
    groups = conn.execute(
        f"""
        SELECT {norm_expr} AS value, COUNT(*) AS identity_count
        FROM track_identity
        WHERE {column} IS NOT NULL AND TRIM({column}) != ''
        GROUP BY {norm_expr}
        HAVING COUNT(*) > 1
        ORDER BY identity_count DESC, value ASC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    out: list[dict[str, object]] = []
    for row in groups:
        value = str(row["value"])
        identities = conn.execute(
            f"""
            SELECT identity_key
            FROM track_identity
            WHERE {norm_expr} = ?
            ORDER BY identity_key ASC
            """,
            (value,),
        ).fetchall()
        out.append(
            {
                label: value,
                "identity_count": int(row["identity_count"]),
                "identity_keys": [str(r["identity_key"]) for r in identities],
            }
        )
    return out


def _write_csv(rows: list[dict[str, object]], out_path: Path) -> Path:
    resolved = out_path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(
        rows,
        key=lambda item: (-int(item["asset_count"]), int(item["identity_id"])),
    )
    with resolved.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow(
                {
                    "identity_id": row["identity_id"],
                    "identity_key": row["identity_key"],
                    "isrc": row["isrc"],
                    "beatport_id": row["beatport_id"],
                    "canonical_artist": row["canonical_artist"],
                    "canonical_title": row["canonical_title"],
                    "asset_count": row["asset_count"],
                    "has_unidentified_key": row["has_unidentified_key"],
                    "missing_core_fields": row["missing_core_fields"],
                    "mixed_quality": row["mixed_quality"],
                    "duration_spread_ms": row["duration_spread_ms"],
                }
            )
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a v3 identity QA report")
    parser.add_argument("--db", required=True, type=Path, help="Path to music_v3.db")
    parser.add_argument("--out", type=Path, help="Write per-identity QA rows to CSV")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Example row limit for summary sections (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument(
        "--include-orphans",
        action="store_true",
        help="Include orphan identities in inconsistency listing (default is active identities only).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if int(args.limit) <= 0:
        print("--limit must be > 0")
        return 2

    db_path = args.db.expanduser().resolve()
    try:
        with _connect_ro(db_path) as conn:
            schema_errors = _schema_errors(conn)
            if schema_errors:
                print(f"v3 db: {db_path}")
                print("FAILED:")
                for err in schema_errors:
                    print(f"- {err}")
                return 1

            rows = _load_identity_rows(conn)
            has_identity_status = _table_exists(conn, "identity_status")
            status_rows = 0
            if has_identity_status:
                status_rows = int(conn.execute("SELECT COUNT(*) FROM identity_status").fetchone()[0])
            counts = {
                "identities_total": len(rows),
                "enriched_identities": sum(0 if _is_blank(r["enriched_at"]) else 1 for r in rows),
                "unidentified_identities": sum(int(r["has_unidentified_key"]) for r in rows),
                "identities_missing_core_fields": sum(int(r["missing_core_fields"]) for r in rows),
                "identities_missing_strong_keys": sum(int(r["missing_strong_keys"]) for r in rows),
            }
            lifecycle_counts = {
                "active_identities": sum(
                    1 for row in rows if str(row["lifecycle_status"]) == "active"
                ),
                "orphan_identities": sum(
                    1 for row in rows if str(row["lifecycle_status"]) == "orphan"
                ),
                "archived_identities": sum(
                    1 for row in rows if str(row["lifecycle_status"]) == "archived"
                ),
                "merged_identities": sum(
                    1 for row in rows if str(row["lifecycle_status"]) == "merged"
                ),
            }
            top_identities = sorted(
                rows,
                key=lambda item: (-int(item["asset_count"]), int(item["identity_id"])),
            )[: int(args.limit)]
            duplicate_isrc = _load_duplicate_groups(
                conn, column="isrc", label="isrc", limit=int(args.limit)
            )
            duplicate_beatport = _load_duplicate_groups(
                conn,
                column="beatport_id",
                label="beatport_id",
                limit=int(args.limit),
            )
            inconsistency_scope = {"active", "orphan"} if args.include_orphans else {"active"}
            inconsistent_identities = [
                r
                for r in rows
                if str(r["lifecycle_status"]) in inconsistency_scope
                and (
                    int(r["duration_spread_ms"]) > DURATION_SPREAD_THRESHOLD_MS
                    or int(r["mixed_quality"]) == 1
                )
            ]
            inconsistent_identities = sorted(
                inconsistent_identities,
                key=lambda item: (-int(item["duration_spread_ms"]), int(item["identity_id"])),
            )[: int(args.limit)]
    except FileNotFoundError as exc:
        print(str(exc))
        return 2
    except sqlite3.DatabaseError as exc:
        print(f"failed to read v3 db: {exc}")
        return 1

    print(f"v3 db: {db_path}")
    print("Counts:")
    for key in (
        "identities_total",
        "enriched_identities",
        "unidentified_identities",
        "identities_missing_core_fields",
        "identities_missing_strong_keys",
    ):
        print(f"  {key}: {counts[key]}")
    print("Lifecycle:")
    for key in (
        "active_identities",
        "orphan_identities",
        "archived_identities",
        "merged_identities",
    ):
        print(f"  {key}: {lifecycle_counts[key]}")
    if has_identity_status:
        print(f"  identity_status_rows: {status_rows}")

    print(f"Top identities by asset_count (limit={int(args.limit)}):")
    if top_identities:
        for row in top_identities:
            print(
                "  "
                f"identity_id={row['identity_id']} "
                f"identity_key={row['identity_key']} "
                f"asset_count={row['asset_count']}"
            )
    else:
        print("  none")

    print(f"Duplicate ISRC groups: {len(duplicate_isrc)}")
    for row in duplicate_isrc:
        keys_joined = ", ".join(str(key) for key in row["identity_keys"])
        print(
            "  "
            f"isrc={row['isrc']} "
            f"identity_count={row['identity_count']} "
            f"identity_keys=[{keys_joined}]"
        )

    print(f"Duplicate beatport_id groups: {len(duplicate_beatport)}")
    for row in duplicate_beatport:
        keys_joined = ", ".join(str(key) for key in row["identity_keys"])
        print(
            "  "
            f"beatport_id={row['beatport_id']} "
            f"identity_count={row['identity_count']} "
            f"identity_keys=[{keys_joined}]"
        )

    scope_label = "active+orphan" if args.include_orphans else "active"
    print(
        f"Inconsistent identities (limit={int(args.limit)}, scope={scope_label}): "
        f"{len(inconsistent_identities)}"
    )
    for row in inconsistent_identities:
        print(
            "  "
            f"identity_id={row['identity_id']} "
            f"identity_key={row['identity_key']} "
            f"duration_spread_ms={row['duration_spread_ms']} "
            f"mixed_quality={row['mixed_quality']}"
        )

    if args.out:
        out_path = _write_csv(rows, args.out)
        print(f"csv_out: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
