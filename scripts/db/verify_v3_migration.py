#!/usr/bin/env python3
"""Verify v2 -> v3 migration structure and aggregate preservation."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.doctor import doctor_v3

MAX_SAMPLE_ROWS = 25


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(str(resolved))
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
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0]) if row else 0


def _count_non_empty_or_zero(conn: sqlite3.Connection, table: str, column: str) -> tuple[int, bool]:
    if not _column_exists(conn, table, column):
        return (0, False)
    row = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND TRIM({column}) != ''"
    ).fetchone()
    return (int(row[0]) if row else 0, True)


def _resolve_doctor_entrypoint() -> str:
    script_path = PROJECT_ROOT / "scripts" / "db" / "doctor_v3.py"
    if script_path.is_file():
        return str(script_path)
    module_path = PROJECT_ROOT / "tagslut" / "db" / "v3" / "doctor.py"
    if module_path.is_file():
        return "tagslut.storage.v3.doctor:doctor_v3"
    return "missing"


def _asset_mismatch_reason(v2_conn: sqlite3.Connection, v3_conn: sqlite3.Connection) -> str:
    reasons: list[str] = []

    if _table_exists(v2_conn, "files") and _column_exists(v2_conn, "files", "path"):
        blank_paths = v2_conn.execute(
            "SELECT COUNT(*) FROM files WHERE path IS NULL OR TRIM(path) = ''"
        ).fetchone()[0]
        duplicate_paths = v2_conn.execute(
            "SELECT COUNT(*) - COUNT(DISTINCT path) FROM files WHERE path IS NOT NULL AND TRIM(path) != ''"
        ).fetchone()[0]
        if int(blank_paths) > 0:
            reasons.append(f"v2 has {int(blank_paths)} empty path rows")
        if int(duplicate_paths) > 0:
            reasons.append(f"v2 has {int(duplicate_paths)} duplicate path rows")

    if _table_exists(v3_conn, "migration_progress"):
        progress = v3_conn.execute(
            "SELECT is_complete FROM migration_progress WHERE id = 1"
        ).fetchone()
        if progress is not None and int(progress[0] or 0) != 1:
            reasons.append("migration_progress.is_complete != 1")

    if not reasons:
        return "no obvious cause detected"
    return "; ".join(reasons)


def _print_counts(*, v2_counts: dict[str, int], v3_counts: dict[str, int]) -> None:
    print("Aggregate work counts:")
    print(f"  v2.assets_total:    {v2_counts['assets_total']}")
    print(f"  v2.integrity_done:  {v2_counts['integrity_done']}")
    print(f"  v2.sha256_done:     {v2_counts['sha256_done']}")
    print(f"  v2.enriched_done:   {v2_counts['enriched_done']}")
    print(f"  v3.assets_total:    {v3_counts['assets_total']}")
    print(f"  v3.integrity_done:  {v3_counts['integrity_done']}")
    print(f"  v3.sha256_done:     {v3_counts['sha256_done']}")
    print(f"  v3.enriched_done:   {v3_counts['enriched_done']}")


def _count_enriched_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path) -> int:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        row = v3_conn.execute(
            """
            SELECT COUNT(*)
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            JOIN asset_link l ON l.asset_id = a.id
            JOIN track_identity t ON t.id = l.identity_id
            WHERE f.enriched_at IS NOT NULL
              AND t.enriched_at IS NULL
            """
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _sample_enriched_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        return v3_conn.execute(
            """
            SELECT
                f.path AS path,
                f.enriched_at AS v2_enriched_at,
                t.identity_key AS identity_key,
                t.enriched_at AS v3_identity_enriched_at
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            JOIN asset_link l ON l.asset_id = a.id
            JOIN track_identity t ON t.id = l.identity_id
            WHERE f.enriched_at IS NOT NULL
              AND t.enriched_at IS NULL
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _count_integrity_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path) -> int:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        row = v3_conn.execute(
            """
            SELECT COUNT(*)
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            WHERE f.integrity_checked_at IS NOT NULL
              AND a.integrity_checked_at IS NULL
            """
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _count_sha256_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path) -> int:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        row = v3_conn.execute(
            """
            SELECT COUNT(*)
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            WHERE f.sha256_checked_at IS NOT NULL
              AND a.sha256_checked_at IS NULL
            """
        ).fetchone()
        return int(row[0]) if row else 0
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _sample_integrity_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        return v3_conn.execute(
            """
            SELECT
                f.path AS path,
                f.integrity_checked_at AS v2_integrity_checked_at,
                a.integrity_checked_at AS v3_integrity_checked_at
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            WHERE f.integrity_checked_at IS NOT NULL
              AND a.integrity_checked_at IS NULL
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _sample_sha256_rows_lost(v3_conn: sqlite3.Connection, v2_path: Path, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    v2_uri = f"file:{quote(str(v2_path.expanduser().resolve()))}?mode=ro"
    v3_conn.execute("ATTACH DATABASE ? AS v2", (v2_uri,))
    try:
        return v3_conn.execute(
            """
            SELECT
                f.path AS path,
                f.sha256_checked_at AS v2_sha256_checked_at,
                a.sha256_checked_at AS v3_sha256_checked_at
            FROM v2.files f
            JOIN asset_file a ON a.path = f.path
            WHERE f.sha256_checked_at IS NOT NULL
              AND a.sha256_checked_at IS NULL
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    finally:
        v3_conn.execute("DETACH DATABASE v2")


def _sample_assets_missing_links(v3_conn: sqlite3.Connection, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    return v3_conn.execute(
        """
        SELECT a.path AS path
        FROM asset_file a
        LEFT JOIN asset_link l ON l.asset_id = a.id
        WHERE l.asset_id IS NULL
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def _sample_assets_multi_links(v3_conn: sqlite3.Connection, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    return v3_conn.execute(
        """
        SELECT a.path AS path, COUNT(*) AS link_count
        FROM asset_file a
        JOIN asset_link l ON l.asset_id = a.id
        GROUP BY a.id, a.path
        HAVING COUNT(*) > 1
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def _sample_orphan_asset_links(v3_conn: sqlite3.Connection, limit: int = MAX_SAMPLE_ROWS) -> list[sqlite3.Row]:
    return v3_conn.execute(
        """
        SELECT l.asset_id AS asset_id, l.identity_id AS identity_id
        FROM asset_link l
        LEFT JOIN asset_file a ON a.id = l.asset_id
        WHERE a.id IS NULL
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def _print_failure_examples(*, title: str, rows: list[sqlite3.Row], columns: tuple[str, ...]) -> None:
    print(f"  {title} (up to {len(rows)} rows):")
    for row in rows:
        parts = [f"{column}={row[column]}" for column in columns]
        print("    " + ", ".join(parts))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify v2 -> v3 migration")
    parser.add_argument("--v2", required=True, type=Path, help="Path to source v2 DB")
    parser.add_argument("--v3", required=True, type=Path, help="Path to target v3 DB")
    parser.add_argument("--strict", action="store_true", help="Enforce strict aggregate preservation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors: list[str] = []

    v2_path = args.v2.expanduser().resolve()
    if not v2_path.exists():
        print(f"v2 db not found: {v2_path}")
        return 2

    v3_path = args.v3.expanduser().resolve()
    if not v3_path.exists():
        print("v3 db not found; run migrate-v2-to-v3")
        return 2

    doctor_entrypoint = _resolve_doctor_entrypoint()
    if doctor_entrypoint == "missing":
        print("doctor tooling missing: add scripts/db/doctor_v3.py or tagslut.storage.v3.doctor")
        return 2
    print(f"doctor entrypoint: {doctor_entrypoint}")

    with _connect_ro(v2_path) as v2_conn, _connect_ro(v3_path) as v3_conn:
        if not _table_exists(v2_conn, "files"):
            print("v2 db missing required table: files")
            return 1

        doctor = doctor_v3(v3_conn)
        if not doctor["ok"]:
            errors.extend(str(item) for item in doctor["errors"])

        v2_integrity_done, has_v2_integrity = _count_non_empty_or_zero(v2_conn, "files", "integrity_checked_at")
        v2_sha256_done, has_v2_sha256 = _count_non_empty_or_zero(v2_conn, "files", "sha256_checked_at")
        v2_enriched_done, has_v2_enriched = _count_non_empty_or_zero(v2_conn, "files", "enriched_at")

        if not has_v2_integrity:
            errors.append("v2.files missing column: integrity_checked_at")
        if not has_v2_sha256:
            errors.append("v2.files missing column: sha256_checked_at")
        if not has_v2_enriched:
            print("NOTE: v2.files missing enriched_at; treating v2.enriched_done as 0")

        v2_counts = {
            "assets_total": _count_rows(v2_conn, "files"),
            "integrity_done": v2_integrity_done,
            "sha256_done": v2_sha256_done,
            "enriched_done": v2_enriched_done,
        }

        v3_counts = {
            "assets_total": int(doctor["counts"]["asset_file_total"]),
            "integrity_done": int(doctor["counts"]["integrity_done"]),
            "sha256_done": int(doctor["counts"]["sha256_done"]),
            "enriched_done": int(doctor["counts"]["enriched_done"]),
        }

        _print_counts(v2_counts=v2_counts, v3_counts=v3_counts)

        if (
            not doctor["missing_tables"]
            and not doctor["missing_columns"]
            and v3_counts["assets_total"] != int(doctor["counts"]["asset_link_total"])
        ):
            missing_link_rows = _sample_assets_missing_links(v3_conn)
            if missing_link_rows:
                _print_failure_examples(
                    title="examples.link_missing_assets",
                    rows=missing_link_rows,
                    columns=("path",),
                )
            multi_link_rows = _sample_assets_multi_links(v3_conn)
            if multi_link_rows:
                _print_failure_examples(
                    title="examples.link_multi_assets",
                    rows=multi_link_rows,
                    columns=("path", "link_count"),
                )
            orphan_link_rows = _sample_orphan_asset_links(v3_conn)
            if orphan_link_rows:
                _print_failure_examples(
                    title="examples.link_orphan_rows",
                    rows=orphan_link_rows,
                    columns=("asset_id", "identity_id"),
                )

        if has_v2_integrity and not doctor["missing_tables"] and not doctor["missing_columns"]:
            integrity_rows_lost = _count_integrity_rows_lost(v3_conn, v2_path)
            print(f"  v3.integrity_rows_lost: {integrity_rows_lost}")
            if integrity_rows_lost > 0:
                sample_rows = _sample_integrity_rows_lost(v3_conn, v2_path)
                _print_failure_examples(
                    title="examples.integrity_rows_lost",
                    rows=sample_rows,
                    columns=("path", "v2_integrity_checked_at", "v3_integrity_checked_at"),
                )
                errors.append(
                    "integrity preservation failed: "
                    f"{integrity_rows_lost} rows have v2.files.integrity_checked_at but v3.asset_file.integrity_checked_at is NULL"
                )

        if has_v2_sha256 and not doctor["missing_tables"] and not doctor["missing_columns"]:
            sha256_rows_lost = _count_sha256_rows_lost(v3_conn, v2_path)
            print(f"  v3.sha256_rows_lost: {sha256_rows_lost}")
            if sha256_rows_lost > 0:
                sample_rows = _sample_sha256_rows_lost(v3_conn, v2_path)
                _print_failure_examples(
                    title="examples.sha256_rows_lost",
                    rows=sample_rows,
                    columns=("path", "v2_sha256_checked_at", "v3_sha256_checked_at"),
                )
                errors.append(
                    "sha256 preservation failed: "
                    f"{sha256_rows_lost} rows have v2.files.sha256_checked_at but v3.asset_file.sha256_checked_at is NULL"
                )

        if has_v2_enriched and not doctor["missing_tables"] and not doctor["missing_columns"]:
            enriched_rows_lost = _count_enriched_rows_lost(v3_conn, v2_path)
            print(f"  v3.enriched_rows_lost: {enriched_rows_lost}")
            if enriched_rows_lost > 0:
                sample_rows = _sample_enriched_rows_lost(v3_conn, v2_path)
                _print_failure_examples(
                    title="examples.enriched_rows_lost",
                    rows=sample_rows,
                    columns=("path", "v2_enriched_at", "identity_key", "v3_identity_enriched_at"),
                )
                errors.append(
                    "enriched_at preservation failed: "
                    f"{enriched_rows_lost} rows have v2.files.enriched_at but linked track_identity.enriched_at is NULL"
                )

        if args.strict:
            if v3_counts["assets_total"] != v2_counts["assets_total"]:
                reason = _asset_mismatch_reason(v2_conn, v3_conn)
                errors.append(
                    "strict: assets_total mismatch "
                    f"(v2={v2_counts['assets_total']}, v3={v3_counts['assets_total']}); {reason}"
                )
            if v3_counts["integrity_done"] < v2_counts["integrity_done"]:
                errors.append(
                    "strict: integrity_done regressed "
                    f"(v2={v2_counts['integrity_done']}, v3={v3_counts['integrity_done']})"
                )
            if v3_counts["sha256_done"] < v2_counts["sha256_done"]:
                errors.append(
                    "strict: sha256_done regressed "
                    f"(v2={v2_counts['sha256_done']}, v3={v3_counts['sha256_done']})"
                )
            if v2_counts["enriched_done"] > 0 and v3_counts["enriched_done"] <= 0:
                errors.append(
                    "strict: enriched_done missing in v3 while v2 had enriched rows"
                )

    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK: v3 migration verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
