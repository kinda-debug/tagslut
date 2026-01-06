#!/usr/bin/env python3
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click


@click.command()
@click.option("--db", required=True, type=click.Path(exists=True, dir_okay=False), help="SQLite DB path")
@click.option("--stale-days", type=int, default=None, help="Treat integrity checks older than N days as stale")
@click.option("--sessions", type=int, default=5, show_default=True, help="How many recent scan sessions to show")
def main(db, stale_days, sessions):
    db_path = Path(db).expanduser().resolve()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        print("=" * 70)
        print("DB DOCTOR")
        print("=" * 70)
        print(f"Database: {db_path}")

        integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
        integrity_status = ", ".join(row[0] for row in integrity_rows)
        print(f"Integrity Check: {integrity_status}")

        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        print("\nTables:")
        for table in tables:
            print(f"  - {table}")

        print("\nCore table counts:")
        for table in ("files", "scan_sessions", "file_scan_runs"):
            if table in tables:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                print(f"  {table}: {count}")
            else:
                print(f"  {table}: (missing)")

        if "files" in tables:
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

        if "scan_sessions" in tables:
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

        if "files" in tables:
            print("\nPending work summary:")
            missing_integrity = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM files
                WHERE mtime IS NOT NULL AND size IS NOT NULL
                  AND integrity_checked_at IS NULL
                """
            ).fetchone()[0]
            print(f"  Metadata present, no integrity result: {missing_integrity}")

            if stale_days is not None:
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

            missing_streaminfo = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM files
                WHERE streaminfo_md5 IS NULL
                  AND (checksum IS NULL OR checksum NOT LIKE 'streaminfo:%')
                """
            ).fetchone()[0]
            print(f"  Missing STREAMINFO MD5: {missing_streaminfo}")

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

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
