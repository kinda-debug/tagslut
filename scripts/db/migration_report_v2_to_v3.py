#!/usr/bin/env python3
"""Generate a read-only migration report comparing v2 and v3 databases."""

from __future__ import annotations

import argparse
import csv
import random
import sqlite3
from pathlib import Path
from urllib.parse import quote

DEFAULT_SAMPLE_SIZE = 200
DEFAULT_SAMPLE_SEED = 20260303


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in cols)


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _count_non_empty(conn: sqlite3.Connection, table: str, column: str) -> int:
    if not _table_exists(conn, table) or not _column_exists(conn, table, column):
        return 0
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND TRIM({column}) != ''"
    ).fetchone()
    return int(row[0]) if row else 0


def _count_v2_unidentified(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "files"):
        return 0
    required = ("canonical_artist", "canonical_title")
    for col in required:
        if not _column_exists(conn, "files", col):
            return 0
    isrc_col = "canonical_isrc" if _column_exists(conn, "files", "canonical_isrc") else "isrc"
    beatport_col = "beatport_id" if _column_exists(conn, "files", "beatport_id") else None
    beatport_expr = (
        f"({beatport_col} IS NULL OR TRIM({beatport_col}) = '') AND " if beatport_col else ""
    )
    row = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM files
        WHERE ({isrc_col} IS NULL OR TRIM({isrc_col}) = '')
          AND {beatport_expr}
              (canonical_artist IS NULL OR TRIM(canonical_artist) = ''
               OR canonical_title IS NULL OR TRIM(canonical_title) = '')
        """
    ).fetchone()
    return int(row[0]) if row else 0


def _count_v3_unidentified(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "track_identity") or not _column_exists(conn, "track_identity", "identity_key"):
        return 0
    row = conn.execute(
        "SELECT COUNT(*) FROM track_identity WHERE identity_key LIKE 'unidentified:%'"
    ).fetchone()
    return int(row[0]) if row else 0


def _load_v2_by_path(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    if not _table_exists(conn, "files"):
        return {}

    columns = ["path"]
    for col in ("integrity_checked_at", "sha256_checked_at", "enriched_at", "canonical_isrc"):
        if _column_exists(conn, "files", col):
            columns.append(col)
        else:
            columns.append(f"NULL AS {col}")

    rows = conn.execute(f"SELECT {', '.join(columns)} FROM files").fetchall()
    return {str(row["path"]): row for row in rows if row["path"] is not None}


def _load_v3_by_path(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    if not _table_exists(conn, "asset_file"):
        return {}
    if not _table_exists(conn, "asset_link") or not _table_exists(conn, "track_identity"):
        rows = conn.execute(
            "SELECT path, integrity_checked_at, sha256_checked_at, NULL AS identity_key, NULL AS enriched_at, NULL AS isrc FROM asset_file"
        ).fetchall()
        return {str(row["path"]): row for row in rows if row["path"] is not None}

    track_identity_cols = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(track_identity)").fetchall()
    }
    enriched_expr = "ti.enriched_at" if "enriched_at" in track_identity_cols else "NULL"
    isrc_expr = "ti.isrc" if "isrc" in track_identity_cols else "NULL"
    rows = conn.execute(
        f"""
        SELECT
            af.path AS path,
            af.integrity_checked_at AS integrity_checked_at,
            af.sha256_checked_at AS sha256_checked_at,
            ti.identity_key AS identity_key,
            {enriched_expr} AS enriched_at,
            {isrc_expr} AS isrc
        FROM asset_file af
        LEFT JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
        LEFT JOIN track_identity ti ON ti.id = al.identity_id
        """
    ).fetchall()
    return {str(row["path"]): row for row in rows if row["path"] is not None}


def _norm(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _isrc_match(v2_isrc: str, v3_isrc: str) -> bool:
    return v2_isrc.upper() == v3_isrc.upper()


def build_report(
    *,
    v2_path: Path,
    v3_path: Path,
    summary_out: Path,
    sample_out: Path,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    seed: int = DEFAULT_SAMPLE_SEED,
) -> tuple[int, int]:
    with _connect_ro(v2_path) as v2_conn, _connect_ro(v3_path) as v3_conn:
        v2_metrics = {
            "assets_count": _count_rows(v2_conn, "files"),
            "with_integrity_checked_at": _count_non_empty(v2_conn, "files", "integrity_checked_at"),
            "with_sha256_checked_at": _count_non_empty(v2_conn, "files", "sha256_checked_at"),
            "with_enriched_at": _count_non_empty(v2_conn, "files", "enriched_at"),
            "with_canonical_isrc": _count_non_empty(v2_conn, "files", "canonical_isrc"),
            "unidentified_identities_count": _count_v2_unidentified(v2_conn),
        }
        v3_metrics = {
            "assets_count": _count_rows(v3_conn, "asset_file"),
            "with_integrity_checked_at": _count_non_empty(v3_conn, "asset_file", "integrity_checked_at"),
            "with_sha256_checked_at": _count_non_empty(v3_conn, "asset_file", "sha256_checked_at"),
            "with_enriched_at": _count_non_empty(v3_conn, "track_identity", "enriched_at"),
            "with_canonical_isrc": _count_non_empty(v3_conn, "track_identity", "isrc"),
            "unidentified_identities_count": _count_v3_unidentified(v3_conn),
        }

        summary_out = summary_out.expanduser().resolve()
        summary_out.parent.mkdir(parents=True, exist_ok=True)
        with summary_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["metric", "v2_count", "v3_count", "delta_v3_minus_v2"],
            )
            writer.writeheader()
            for metric in (
                "assets_count",
                "with_integrity_checked_at",
                "with_sha256_checked_at",
                "with_enriched_at",
                "with_canonical_isrc",
                "unidentified_identities_count",
            ):
                v2_val = int(v2_metrics.get(metric, 0))
                v3_val = int(v3_metrics.get(metric, 0))
                writer.writerow(
                    {
                        "metric": metric,
                        "v2_count": v2_val,
                        "v3_count": v3_val,
                        "delta_v3_minus_v2": v3_val - v2_val,
                    }
                )

        v2_rows = _load_v2_by_path(v2_conn)
        v3_rows = _load_v3_by_path(v3_conn)
        matched_paths = sorted(set(v2_rows.keys()) & set(v3_rows.keys()))
        rng = random.Random(seed)
        sample_paths = matched_paths
        if len(sample_paths) > sample_size:
            sample_paths = rng.sample(sample_paths, sample_size)
        sample_paths = sorted(sample_paths)

        sample_out = sample_out.expanduser().resolve()
        sample_out.parent.mkdir(parents=True, exist_ok=True)
        with sample_out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "path",
                    "v2_integrity_checked_at",
                    "v3_integrity_checked_at",
                    "integrity_checked_match",
                    "v2_sha256_checked_at",
                    "v3_sha256_checked_at",
                    "sha256_checked_match",
                    "v2_enriched_at",
                    "v3_enriched_at",
                    "enriched_at_match",
                    "v2_canonical_isrc",
                    "v3_isrc",
                    "canonical_isrc_match",
                    "v3_identity_key",
                ],
            )
            writer.writeheader()
            for path in sample_paths:
                v2_row = v2_rows[path]
                v3_row = v3_rows[path]
                v2_integrity = _norm(v2_row["integrity_checked_at"])
                v3_integrity = _norm(v3_row["integrity_checked_at"])
                v2_sha = _norm(v2_row["sha256_checked_at"])
                v3_sha = _norm(v3_row["sha256_checked_at"])
                v2_enriched = _norm(v2_row["enriched_at"])
                v3_enriched = _norm(v3_row["enriched_at"])
                v2_isrc = _norm(v2_row["canonical_isrc"])
                v3_isrc = _norm(v3_row["isrc"])
                writer.writerow(
                    {
                        "path": path,
                        "v2_integrity_checked_at": v2_integrity,
                        "v3_integrity_checked_at": v3_integrity,
                        "integrity_checked_match": int(v2_integrity == v3_integrity),
                        "v2_sha256_checked_at": v2_sha,
                        "v3_sha256_checked_at": v3_sha,
                        "sha256_checked_match": int(v2_sha == v3_sha),
                        "v2_enriched_at": v2_enriched,
                        "v3_enriched_at": v3_enriched,
                        "enriched_at_match": int(v2_enriched == v3_enriched),
                        "v2_canonical_isrc": v2_isrc,
                        "v3_isrc": v3_isrc,
                        "canonical_isrc_match": int(_isrc_match(v2_isrc, v3_isrc)) if v2_isrc and v3_isrc else 0,
                        "v3_identity_key": _norm(v3_row["identity_key"]),
                    }
                )

    return (len(matched_paths), len(sample_paths))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate migration report from v2 and v3 DBs")
    parser.add_argument("--v2", required=True, type=Path, help="Path to source v2 DB")
    parser.add_argument("--v3", required=True, type=Path, help="Path to migrated v3 DB")
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path("artifacts/migration_report_v2_to_v3_summary.csv"),
        help="Output CSV path for summary metrics",
    )
    parser.add_argument(
        "--sample-out",
        type=Path,
        default=Path("artifacts/migration_report_v2_to_v3_sample.csv"),
        help="Output CSV path for sampled row comparisons",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Number of sampled rows for v2/v3 comparison (default: {DEFAULT_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SAMPLE_SEED,
        help=f"Deterministic random seed (default: {DEFAULT_SAMPLE_SEED})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.sample_size <= 0:
        raise SystemExit("--sample-size must be > 0")

    matched, sampled = build_report(
        v2_path=args.v2,
        v3_path=args.v3,
        summary_out=args.summary_out,
        sample_out=args.sample_out,
        sample_size=int(args.sample_size),
        seed=int(args.seed),
    )
    print(f"Summary CSV: {args.summary_out.expanduser().resolve()}")
    print(f"Sample CSV:  {args.sample_out.expanduser().resolve()}")
    print(f"Matched paths: {matched}")
    print(f"Sampled rows:  {sampled}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

