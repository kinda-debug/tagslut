#!/usr/bin/env python3
"""Inspect the music_v3 SQLite DB and export a diagnostic bundle."""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

DB_PATH = Path("/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-03-04/music_v3.db")
OUTPUT_DIR = Path("diagnostics")
SAMPLE_LIMIT = 100
MASTER_PATH_FILTER = "%MASTER_LIBRARY%"
FLAGGED_UNION_CLAUSE = (
    "f.is_dj_material = 1 OR (f.dj_pool_path IS NOT NULL AND TRIM(f.dj_pool_path) <> '')"
)
DJ_POOL_PATH_CLAUSE = "f.dj_pool_path IS NOT NULL AND TRIM(f.dj_pool_path) <> ''"


def connect_ro(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Database not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def row_to_plain_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def table_or_view_exists(conn: sqlite3.Connection, name: str, obj_type: str | None = None) -> bool:
    query = "SELECT 1 FROM sqlite_master WHERE name = ?"
    params: list[object] = [name]
    if obj_type is not None:
        query += " AND type = ?"
        params.append(obj_type)
    row = conn.execute(query, params).fetchone()
    return row is not None


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row["name"]) for row in rows]


def fetch_scalar(conn: sqlite3.Connection, query: str) -> int:
    row = conn.execute(query).fetchone()
    if row is None:
        return 0
    value = row[0]
    return int(value or 0)


def fetch_optional_scalar(
    conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()
) -> int | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    value = row[0]
    if value is None:
        return None
    return int(value)


def export_schema_inventory(conn: sqlite3.Connection, output_dir: Path) -> None:
    rows = conn.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    payload = {"indexes": [], "tables": [], "views": []}
    for row in rows:
        entry = {"name": row["name"], "sql": row["sql"], "type": row["type"]}
        if row["type"] == "table":
            payload["tables"].append(entry)
        elif row["type"] == "view":
            payload["views"].append(entry)
        elif row["type"] == "index":
            payload["indexes"].append(entry)
    write_json(output_dir / "schema_inventory.json", payload)


def export_db_stats(conn: sqlite3.Connection, output_dir: Path) -> dict[str, int]:
    payload = {
        "files": fetch_scalar(conn, "SELECT COUNT(*) FROM files"),
        "asset_file": fetch_scalar(conn, "SELECT COUNT(*) FROM asset_file"),
        "asset_link": fetch_scalar(conn, "SELECT COUNT(*) FROM asset_link"),
        "track_identity": fetch_scalar(conn, "SELECT COUNT(*) FROM track_identity"),
        "provenance_event": fetch_scalar(conn, "SELECT COUNT(*) FROM provenance_event"),
    }
    write_json(output_dir / "db_stats.json", payload)
    return payload


def export_dj_cohort_stats(conn: sqlite3.Connection, output_dir: Path) -> dict[str, int]:
    payload = {
        "flagged_union": fetch_scalar(
            conn,
            f"""
            SELECT COUNT(*) AS flagged_union
            FROM files f
            WHERE {FLAGGED_UNION_CLAUSE}
            """,
        ),
        "flagged_master": 0,
    }
    payload["flagged_master"] = fetch_optional_scalar(
        conn,
        f"""
        SELECT COUNT(*) AS flagged_master
        FROM files f
        WHERE ({FLAGGED_UNION_CLAUSE})
          AND f.path LIKE ?
        """,
        (MASTER_PATH_FILTER,),
    ) or 0
    write_json(output_dir / "dj_cohort_stats.json", payload)
    return payload


def export_identity_coverage(conn: sqlite3.Connection, output_dir: Path) -> dict[str, int]:
    identity_columns = set(get_table_columns(conn, "track_identity"))
    identity_pk = "identity_id" if "identity_id" in identity_columns else "id"
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS flagged_master_total,
            SUM(CASE WHEN ti.{identity_pk} IS NOT NULL THEN 1 ELSE 0 END) AS flagged_master_with_identity
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al ON al.asset_id = af.id
        LEFT JOIN track_identity ti ON ti.{identity_pk} = al.identity_id
        WHERE ({FLAGGED_UNION_CLAUSE})
          AND f.path LIKE ?
        """,
        (MASTER_PATH_FILTER,),
    ).fetchone()
    total = int(row["flagged_master_total"] or 0)
    with_identity = int(row["flagged_master_with_identity"] or 0)
    payload = {
        "flagged_master_total": total,
        "flagged_master_with_identity": with_identity,
        "flagged_master_without_identity": total - with_identity,
    }
    write_json(output_dir / "identity_coverage.json", payload)
    return payload


def export_legacy_cache_stats(conn: sqlite3.Connection, output_dir: Path) -> dict[str, int]:
    payload = {
        "legacy_cache_total": fetch_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM files
            WHERE dj_pool_path IS NOT NULL
              AND TRIM(dj_pool_path) <> ''
            """,
        ),
        "flagged_master_using_legacy_cache": fetch_optional_scalar(
            conn,
            f"""
            SELECT COUNT(*)
            FROM files f
            WHERE f.path LIKE ?
              AND {DJ_POOL_PATH_CLAUSE}
              AND ({FLAGGED_UNION_CLAUSE})
            """,
            (MASTER_PATH_FILTER,),
        )
        or 0,
    }
    write_json(output_dir / "legacy_cache_stats.json", payload)
    return payload


def export_provenance_stats(conn: sqlite3.Connection, output_dir: Path) -> dict[str, int]:
    payload = {
        "dj_export_events": fetch_scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM provenance_event
            WHERE event_type = 'dj_export'
            """,
        )
    }
    write_json(output_dir / "provenance_stats.json", payload)
    return payload


def export_candidate_view_stats(conn: sqlite3.Connection, output_dir: Path) -> dict[str, object]:
    payload: dict[str, object] = {}
    for view_name in ("v_dj_pool_candidates_v3", "v_dj_export_metadata_v1"):
        exists = table_or_view_exists(conn, view_name, "view")
        payload[view_name] = {
            "count": fetch_scalar(conn, f"SELECT COUNT(*) FROM {view_name}") if exists else None,
            "exists": exists,
        }
    write_json(output_dir / "candidate_view_stats.json", payload)
    return payload


def export_cohort_health(
    conn: sqlite3.Connection,
    output_dir: Path,
    dj_cohort: dict[str, int],
) -> dict[str, object]:
    split_row = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN f.is_dj_material = 1 THEN 1 ELSE 0 END) AS is_dj_material_count,
            SUM(CASE WHEN {DJ_POOL_PATH_CLAUSE} THEN 1 ELSE 0 END) AS dj_pool_path_count,
            SUM(CASE WHEN {FLAGGED_UNION_CLAUSE} THEN 1 ELSE 0 END) AS flagged_union_count
        FROM files f
        WHERE f.path LIKE ?
        """,
        (MASTER_PATH_FILTER,),
    ).fetchone()

    identity_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS cohort_total,
            SUM(CASE WHEN al.identity_id IS NOT NULL THEN 1 ELSE 0 END) AS cohort_with_identity,
            SUM(CASE WHEN al.identity_id IS NULL THEN 1 ELSE 0 END) AS cohort_without_identity
        FROM files f
        LEFT JOIN asset_file af ON af.path = f.path
        LEFT JOIN asset_link al ON al.asset_id = af.id
        WHERE ({FLAGGED_UNION_CLAUSE})
          AND f.path LIKE ?
        """,
        (MASTER_PATH_FILTER,),
    ).fetchone()

    provenance_count = fetch_optional_scalar(
        conn,
        f"""
        SELECT
            COUNT(DISTINCT f.path) AS cohort_with_dj_export_provenance
        FROM files f
        JOIN asset_file af ON af.path = f.path
        JOIN asset_link al ON al.asset_id = af.id
        JOIN provenance_event pe ON pe.identity_id = al.identity_id
        WHERE ({FLAGGED_UNION_CLAUSE})
          AND f.path LIKE ?
          AND pe.event_type = 'dj_export'
        """,
        (MASTER_PATH_FILTER,),
    ) or 0

    cohort_total = int(identity_row["cohort_total"] or 0)
    cohort_with_identity = int(identity_row["cohort_with_identity"] or 0)
    cohort_without_identity = int(identity_row["cohort_without_identity"] or 0)
    identity_coverage_pct = 0.0
    if cohort_total > 0:
        identity_coverage_pct = round((cohort_with_identity / cohort_total) * 100, 1)

    dj_pool_path_count = int(split_row["dj_pool_path_count"] or 0)
    payload = {
        "cohort_definition": "files.dj_pool_path IS NOT NULL AND TRIM(files.dj_pool_path) <> ''",
        "master_restricted": True,
        "flagged_union_count": int(split_row["flagged_union_count"] or 0),
        "flagged_master_count": int(dj_cohort["flagged_master"]),
        "is_dj_material_count": int(split_row["is_dj_material_count"] or 0),
        "dj_pool_path_count": dj_pool_path_count,
        "cohort_without_identity": cohort_without_identity,
        "cohort_with_identity": cohort_with_identity,
        "identity_coverage_pct": identity_coverage_pct,
        "cohort_with_dj_export_provenance": provenance_count,
        "cohort_without_dj_export_provenance": cohort_total - provenance_count,
        "legacy_cache_only_rows": max(dj_pool_path_count - provenance_count, 0),
        "transcode_required_rows": cohort_total - provenance_count,
        "notes": [
            "Current cohort is export-backed, not semantic is_dj_material cohort",
            "Current cohort is fully identity-backed" if cohort_without_identity == 0 else "Current cohort has rows missing identity links",
            (
                "Current cohort is fully export-backed and deduped at identity layer"
                if provenance_count == cohort_total
                else "Current cohort has rows without dj_export provenance"
            ),
        ],
    }
    write_json(output_dir / "cohort_health.json", payload)
    return payload


def export_cohort_duplicates(conn: sqlite3.Connection, output_dir: Path) -> dict[str, object]:
    rows = conn.execute(
        f"""
        SELECT
            al.identity_id,
            COUNT(*) AS row_count
        FROM files f
        JOIN asset_file af ON af.path = f.path
        JOIN asset_link al ON al.asset_id = af.id
        WHERE ({FLAGGED_UNION_CLAUSE})
          AND f.path LIKE ?
        GROUP BY al.identity_id
        HAVING COUNT(*) > 1
        ORDER BY row_count DESC, al.identity_id ASC
        """,
        (MASTER_PATH_FILTER,),
    ).fetchall()
    duplicate_rows = [
        {"identity_id": int(row["identity_id"]), "row_count": int(row["row_count"] or 0)}
        for row in rows
    ]
    payload = {
        "duplicate_identity_count": len(duplicate_rows),
        "duplicate_master_path_count": sum(int(row["row_count"]) for row in duplicate_rows),
        "duplicate_rows": duplicate_rows,
    }
    write_json(output_dir / "cohort_duplicates.json", payload)
    return payload


def export_sample_csv(conn: sqlite3.Connection, table_name: str, output_path: Path, limit: int) -> None:
    rows = conn.execute(f"SELECT * FROM {table_name} LIMIT ?", (int(limit),)).fetchall()
    columns = get_table_columns(conn, table_name)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row_to_plain_dict(row))


def print_summary(
    db_stats: dict[str, int],
    dj_cohort: dict[str, int],
    identity_coverage: dict[str, int],
    legacy_cache: dict[str, int],
    provenance: dict[str, int],
) -> None:
    total = identity_coverage["flagged_master_total"]
    covered = identity_coverage["flagged_master_with_identity"]
    coverage_pct = 0
    if total > 0:
        coverage_pct = round((covered / total) * 100)

    print(f"FILES: {db_stats['files']}")
    print(f"DJ FLAGGED: {dj_cohort['flagged_union']}")
    print(f"FLAGGED MASTER: {dj_cohort['flagged_master']}")
    print(f"IDENTITY COVERAGE: {coverage_pct}%")
    print(f"LEGACY CACHE: {legacy_cache['legacy_cache_total']}")
    print(f"DJ_EXPORT EVENTS: {provenance['dj_export_events']}")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with connect_ro(DB_PATH) as conn:
            export_schema_inventory(conn, OUTPUT_DIR)
            db_stats = export_db_stats(conn, OUTPUT_DIR)
            dj_cohort = export_dj_cohort_stats(conn, OUTPUT_DIR)
            identity_coverage = export_identity_coverage(conn, OUTPUT_DIR)
            legacy_cache = export_legacy_cache_stats(conn, OUTPUT_DIR)
            provenance = export_provenance_stats(conn, OUTPUT_DIR)
            export_candidate_view_stats(conn, OUTPUT_DIR)
            export_cohort_health(conn, OUTPUT_DIR, dj_cohort)
            export_cohort_duplicates(conn, OUTPUT_DIR)
            export_sample_csv(conn, "files", OUTPUT_DIR / "sample_files.csv", SAMPLE_LIMIT)
            export_sample_csv(conn, "track_identity", OUTPUT_DIR / "sample_identity.csv", SAMPLE_LIMIT)
            export_sample_csv(conn, "provenance_event", OUTPUT_DIR / "sample_provenance.csv", SAMPLE_LIMIT)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"SQLite error: {exc}", file=sys.stderr)
        return 1

    print_summary(db_stats, dj_cohort, identity_coverage, legacy_cache, provenance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
