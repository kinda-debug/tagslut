#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import sqlite3

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dedupe.utils.config import get_config
from dedupe.utils.db import open_db, resolve_db_path

CORE_TABLES = (
    "files",
    "library_files",
    "scan_sessions",
    "file_scan_runs",
    "schema_migrations",
)


@dataclass(frozen=True)
class DbProfile:
    path: Path
    source: str
    size_bytes: int
    mtime: float
    inode: int
    quick_hash: str
    tables: list[str]
    row_counts: dict[str, Optional[int]]
    files_table: Optional[str]
    files_columns: Optional[list[str]]
    library_zone_counts: Optional[list[tuple[str | None, str | None, int]]]
    newest_rows: Optional[list[tuple[float | None, str]]]
    user_version: Optional[int]


def _format_mtime(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(value))


def _quick_hash(path: Path, size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(size))
    return digest.hexdigest()


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]


def _count_table(conn: sqlite3.Connection, table: str) -> Optional[int]:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None


def _library_zone_counts(
    conn: sqlite3.Connection, table: str, columns: Iterable[str]
) -> Optional[list[tuple[str | None, str | None, int]]]:
    if "library" not in columns or "zone" not in columns:
        return None
    try:
        rows = conn.execute(
            f"""
            SELECT library, zone, COUNT(*) AS count
            FROM {table}
            GROUP BY library, zone
            ORDER BY library, zone
            """
        ).fetchall()
    except sqlite3.Error:
        return None
    return [(row["library"], row["zone"], int(row["count"])) for row in rows]


def _newest_rows(
    conn: sqlite3.Connection, table: str, columns: Iterable[str], limit: int
) -> Optional[list[tuple[float | None, str]]]:
    if "path" not in columns or "mtime" not in columns:
        return None
    try:
        rows = conn.execute(
            f"""
            SELECT path, mtime
            FROM {table}
            ORDER BY mtime DESC, path DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error:
        return None
    return [(row["mtime"], row["path"]) for row in rows]


def _profile(path: str, label: str, limit: int) -> DbProfile:
    resolution = resolve_db_path(
        path,
        config=get_config(),
        purpose="read",
        allow_create=False,
        source_label=label,
    )
    conn = open_db(resolution)
    try:
        tables = _list_tables(conn)
        row_counts = {
            table: _count_table(conn, table) if table in tables else None
            for table in CORE_TABLES
        }
        files_table = None
        if "files" in tables:
            files_table = "files"
        elif "library_files" in tables:
            files_table = "library_files"
        files_columns = _table_columns(conn, files_table) if files_table else None
        library_zone_counts = (
            _library_zone_counts(conn, files_table, files_columns)
            if files_table and files_columns
            else None
        )
        newest_rows = (
            _newest_rows(conn, files_table, files_columns, limit)
            if files_table and files_columns
            else None
        )
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    stat = os.stat(resolution.path)
    return DbProfile(
        path=resolution.path,
        source=resolution.source,
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        inode=stat.st_ino,
        quick_hash=_quick_hash(resolution.path),
        tables=tables,
        row_counts=row_counts,
        files_table=files_table,
        files_columns=files_columns,
        library_zone_counts=library_zone_counts,
        newest_rows=newest_rows,
        user_version=user_version,
    )


def _print_profile(profile: DbProfile, label: str, limit: int) -> None:
    print(f"=== {label} ===")
    print(f"path: {profile.path}")
    print(f"source: {profile.source}")
    print(f"size_bytes: {profile.size_bytes}")
    print(f"mtime: {profile.mtime:.0f} ({_format_mtime(profile.mtime)})")
    print(f"inode: {profile.inode}")
    print(f"quick_hash_1MiB: {profile.quick_hash}")
    print(f"user_version: {profile.user_version}")
    tables = ", ".join(profile.tables) if profile.tables else "(none)"
    print(f"tables: {tables}")
    print("row_counts:")
    for table in CORE_TABLES:
        if table not in profile.tables:
            value = "missing"
        else:
            count = profile.row_counts.get(table)
            value = "error" if count is None else str(count)
        print(f"  {table}: {value}")
    if profile.files_table:
        print(f"files_columns (table={profile.files_table}):")
        if profile.files_columns:
            print(f"  {', '.join(profile.files_columns)}")
        else:
            print("  unavailable")
    else:
        print("files_columns: unavailable (no files-like table)")
    print("library_zone_counts:")
    if profile.library_zone_counts is None:
        print("  unavailable (missing files table or columns)")
    else:
        for library, zone, count in profile.library_zone_counts:
            lib = library if library is not None else "(none)"
            zn = zone if zone is not None else "(none)"
            print(f"  {lib}\t{zn}\t{count}")
    print(f"newest_rows (limit={limit}):")
    if profile.newest_rows is None:
        print("  unavailable (missing path/mtime columns)")
    else:
        for mtime, path in profile.newest_rows:
            if mtime is None:
                mtime_str = "None"
            else:
                mtime_str = f"{mtime:.0f}"
            print(f"  {mtime_str}\t{path}")


def _print_column_diff(a: DbProfile, b: DbProfile) -> bool:
    print("=== Files Column Diff ===")
    if not a.files_columns or not b.files_columns:
        print("files columns: unavailable (missing files-like table)")
        return True
    a_cols = set(a.files_columns)
    b_cols = set(b.files_columns)
    missing_in_a = sorted(b_cols - a_cols)
    missing_in_b = sorted(a_cols - b_cols)
    if not missing_in_a and not missing_in_b:
        print("files columns: match")
        return False
    if missing_in_a:
        print(f"missing_in_a: {', '.join(missing_in_a)}")
    else:
        print("missing_in_a: (none)")
    if missing_in_b:
        print(f"missing_in_b: {', '.join(missing_in_b)}")
    else:
        print("missing_in_b: (none)")
    return True


def _print_copy_detection(a: DbProfile, b: DbProfile) -> None:
    print("=== Copy Detection ===")
    size_match = a.size_bytes == b.size_bytes
    inode_match = a.inode == b.inode
    mtime_match = abs(a.mtime - b.mtime) < 0.0001
    hash_match = a.quick_hash == b.quick_hash
    print(f"size_match: {'yes' if size_match else 'no'}")
    print(f"inode_match: {'yes' if inode_match else 'no'}")
    print(f"mtime_match: {'yes' if mtime_match else 'no'}")
    print(f"quick_hash_match: {'yes' if hash_match else 'no'}")
    if size_match and inode_match and mtime_match:
        verdict = "same file (inode/mtime match)"
    elif size_match and hash_match:
        verdict = "likely same content (size + quick hash match)"
    else:
        verdict = "different"
    print(f"verdict: {verdict}")


def _print_merge_recommendation(a: DbProfile, b: DbProfile, schema_diff: bool) -> None:
    print("=== Merge Recommendation (Read-Only) ===")
    print("status: REFUSE")
    if schema_diff:
        print("reason: These DBs are not merge-compatible because schema differs.")
    a_sessions = (
        "scan_sessions" in a.tables
        and (a.row_counts.get("scan_sessions") or 0) > 0
    )
    b_sessions = (
        "scan_sessions" in b.tables
        and (b.row_counts.get("scan_sessions") or 0) > 0
    )
    if not b_sessions:
        print("reason: DB B lacks sessions; migrate it first before any consolidation.")
    if not a_sessions:
        print("reason: DB A lacks sessions; migrate it first before any consolidation.")
    if not schema_diff and a_sessions and b_sessions:
        print("note: Schemas appear compatible, but merges are still forbidden.")
    print("note: Never backfill sessions from logs.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only SQLite DB comparison.")
    ap.add_argument("--a", required=True, help="Path to DB A.")
    ap.add_argument("--b", required=True, help="Path to DB B.")
    ap.add_argument(
        "--sample",
        type=int,
        default=5,
        help="Number of newest rows to sample (default: 5).",
    )
    args = ap.parse_args()

    try:
        a_profile = _profile(args.a, "cli-a", args.sample)
        b_profile = _profile(args.b, "cli-b", args.sample)
    except (ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _print_profile(a_profile, "DB A", args.sample)
    print()
    _print_profile(b_profile, "DB B", args.sample)
    print()
    schema_diff = _print_column_diff(a_profile, b_profile)
    print()
    _print_copy_detection(a_profile, b_profile)
    print()
    _print_merge_recommendation(a_profile, b_profile, schema_diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
