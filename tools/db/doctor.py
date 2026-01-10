#!/usr/bin/env python3
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from dedupe.utils.config import get_config
from dedupe.utils.db import open_db, resolve_db_path


EXPECTED_FILES_COLUMNS = {
    "path",
    "library",
    "zone",
    "mtime",
    "size",
    "checksum",
    "streaminfo_md5",
    "sha256",
    "integrity_state",
    "integrity_checked_at",
    "streaminfo_checked_at",
    "sha256_checked_at",
    "flac_ok",
}

SCAN_SESSION_REQUIRED_COLUMNS = {
    "id",
    "started_at",
    "ended_at",
    "status",
    "scan_integrity",
    "scan_hash",
    "recheck",
    "incremental",
    "force_all",
    "discovered",
    "considered",
    "skipped",
    "succeeded",
    "failed",
    "root_path",
    "paths_source",
}

SCAN_SESSION_EXPECTED_COLUMNS = SCAN_SESSION_REQUIRED_COLUMNS | {
    "finished_at",
    "db_path",
    "library",
    "zone",
    "paths_from_file",
    "scan_limit",
    "updated",
    "host",
}


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _print_missing_columns(table: str, missing: list[str]) -> None:
    if not missing:
        return
    print(f"  - {table}: missing columns -> {', '.join(missing)}")


@click.command()
@click.option("--db", required=False, type=click.Path(dir_okay=False), help="SQLite DB path")
@click.option("--stale-days", type=int, default=None, help="Treat integrity checks older than N days as stale")
@click.option("--sessions", type=int, default=5, show_default=True, help="How many recent scan sessions to show")
def main(db: str | None, stale_days: int | None, sessions: int) -> None:
    app_config = get_config()
    try:
        resolution = resolve_db_path(
            db,
            config=app_config,
            repo_root=REPO_ROOT,
            purpose="read",
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    db_path = resolution.path
    try:
        conn = open_db(resolution)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        print("=" * 70)
        print("DB DOCTOR")
        print("=" * 70)
        print(f"Database: {db_path}")

        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
        integrity_status = ", ".join(row[0] for row in integrity_rows)
        print(f"Integrity Check: {integrity_status}")

        tables = _list_tables(conn)
        print("\nTables:")
        for table in tables:
            print(f"  - {table}")

        missing_tables = [t for t in ("files", "scan_sessions", "file_scan_runs") if t not in tables]
        missing_columns: list[str] = []

        if "files" in tables:
            files_columns = _table_columns(conn, "files")
            missing_columns = sorted(EXPECTED_FILES_COLUMNS - files_columns)

        if missing_tables or missing_columns:
            print("\nSchema Gaps:")
            for table in missing_tables:
                print(f"  - {table}: (missing table)")
            _print_missing_columns("files", missing_columns)
            print(
                "\nMigration required: run schema migrations (init_db) before any write operations."
            )
            print("Writes should be refused while schema gaps remain.")

        print("\nCore table counts:")
        for table in ("files", "scan_sessions", "file_scan_runs"):
            if table in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {count}")
            else:
                print(f"  {table}: (missing)")

        if "files" in tables:
            files_columns = _table_columns(conn, "files")
            if {"library", "zone"} <= files_columns:
                print("\nLibrary/Zone counts:")
                rows = conn.execute(
                    """
                    SELECT library, zone, COUNT(*) AS cnt
                    FROM files
                    GROUP BY library, zone
                    ORDER BY library, zone
                    """
                ).fetchall()
                for row in rows:
                    library = row["library"] if row["library"] else "(none)"
                    zone = row["zone"] if row["zone"] else "(none)"
                    print(f"  {library} / {zone}: {row['cnt']}")
            else:
                missing = sorted({"library", "zone"} - files_columns)
                print("\nLibrary/Zone counts: skipped (missing columns)")
                print(f"  missing: {', '.join(missing)}")

        if "scan_sessions" in tables:
            session_cols = _table_columns(conn, "scan_sessions")
            missing_expected = sorted(SCAN_SESSION_EXPECTED_COLUMNS - session_cols)
            if missing_expected:
                print("\nScan session schema gaps:")
                print(f"  missing: {', '.join(missing_expected)}")
            if SCAN_SESSION_REQUIRED_COLUMNS <= session_cols:
                print("\nRecent scan sessions:")
                rows = conn.execute(
                    """
                    SELECT id, started_at, ended_at, status, scan_integrity, scan_hash,
                           recheck, incremental, force_all, discovered, considered, skipped,
                           succeeded, failed, root_path, paths_source
                    FROM scan_sessions
                    ORDER BY started_at DESC, id DESC
                    LIMIT ?
                    """,
                    (sessions,),
                ).fetchall()
                if not rows:
                    print("  (none)")
                else:
                    for row in rows:
                        flags = (
                            f"integrity={row['scan_integrity']}",
                            f"hash={row['scan_hash']}",
                            f"recheck={row['recheck']}",
                            f"incremental={row['incremental']}",
                            f"force_all={row['force_all']}",
                        )
                        print(
                            "  "
                            f"#{row['id']} {row['status']} | {row['started_at']} -> {row['ended_at']}"
                        )
                        print(
                            "     "
                            f"discovered={row['discovered']} considered={row['considered']} "
                            f"skipped={row['skipped']} succeeded={row['succeeded']} failed={row['failed']}"
                        )
                        print(f"     flags: {', '.join(flags)}")
                        if row["root_path"]:
                            print(f"     root: {row['root_path']}")
                        if row["paths_source"]:
                            print(f"     paths: {row['paths_source']}")
            else:
                missing = sorted(SCAN_SESSION_REQUIRED_COLUMNS - session_cols)
                print("\nRecent scan sessions: skipped (missing columns)")
                print(f"  missing: {', '.join(missing)}")

        if "files" in tables:
            files_columns = _table_columns(conn, "files")
            print("\nPending work summary:")
            if {"mtime", "size", "integrity_checked_at"} <= files_columns:
                missing_integrity = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM files
                    WHERE mtime IS NOT NULL AND size IS NOT NULL
                      AND integrity_checked_at IS NULL
                    """
                ).fetchone()[0]
                print(f"  Metadata present, no integrity result: {missing_integrity}")
            else:
                missing = sorted({"mtime", "size", "integrity_checked_at"} - files_columns)
                print("  Metadata present, no integrity result: skipped")
                print(f"    missing: {', '.join(missing)}")

            if stale_days is not None:
                if "integrity_checked_at" in files_columns:
                    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
                    cutoff_str = cutoff.isoformat(timespec="seconds")
                    stale_integrity = conn.execute(
                        """
                        SELECT COUNT(*) AS cnt
                        FROM files
                        WHERE integrity_checked_at IS NOT NULL
                          AND integrity_checked_at < ?
                        """,
                        (cutoff_str,),
                    ).fetchone()[0]
                    print(f"  Integrity older than {stale_days} days: {stale_integrity}")
                else:
                    print(f"  Integrity older than {stale_days} days: skipped (missing integrity_checked_at)")

            if {"streaminfo_md5", "checksum"} <= files_columns:
                missing_streaminfo = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM files
                    WHERE streaminfo_md5 IS NULL
                      AND (checksum IS NULL OR checksum NOT LIKE 'streaminfo:%')
                    """
                ).fetchone()[0]
                print(f"  Missing STREAMINFO MD5: {missing_streaminfo}")
            else:
                missing = sorted({"streaminfo_md5", "checksum"} - files_columns)
                print("  Missing STREAMINFO MD5: skipped")
                print(f"    missing: {', '.join(missing)}")

            if {"sha256", "checksum"} <= files_columns:
                missing_sha256 = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM files
                    WHERE sha256 IS NULL
                      AND (
                        checksum IS NULL
                        OR checksum = 'NOT_SCANNED'
                        OR checksum LIKE 'streaminfo:%'
                      )
                    """
                ).fetchone()[0]
                print(f"  Missing SHA256: {missing_sha256}")
            else:
                missing = sorted({"sha256", "checksum"} - files_columns)
                print("  Missing SHA256: skipped")
                print(f"    missing: {', '.join(missing)}")

            print("\nAssumptions:")
            print("  - Checksums prefixed with 'streaminfo:' are treated as STREAMINFO MD5.")
            print("  - Checksums prefixed with 'sha256:' are treated as full-file SHA256.")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
