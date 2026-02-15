#!/usr/bin/env python3
"""Backfill v3 asset/identity/link rows from the legacy files table."""

from __future__ import annotations

import argparse
import json
import sqlite3

from tagslut.storage.schema import init_db
from tagslut.storage.v3 import dual_write_registered_file
from tagslut.utils.db import resolve_db_path


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill v3 asset/identity/link tables from files rows."
    )
    parser.add_argument("--db", required=True, help="SQLite DB path")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write backfill rows (default: dry-run report only)",
    )
    parser.add_argument("--limit", type=int, help="Process first N rows only")
    args = parser.parse_args()

    resolution = resolve_db_path(
        args.db,
        purpose="write" if args.execute else "read",
        allow_create=bool(args.execute),
    )
    db_path = resolution.path

    conn = sqlite3.connect(str(db_path))
    try:
        if args.execute:
            init_db(conn)

        query = """
        SELECT path, sha256, streaminfo_md5, checksum, size, mtime, duration,
               sample_rate, bit_depth, bitrate, library, zone, download_source,
               download_date, mgmt_status, metadata_json, duration_ref_ms,
               duration_ref_source
        FROM files
        ORDER BY path
        """
        if args.limit:
            query += f" LIMIT {int(args.limit)}"
        rows = conn.execute(query).fetchall()

        processed = 0
        linked = 0
        for row in rows:
            metadata = _parse_metadata(row[15])
            if args.execute:
                _, identity_id = dual_write_registered_file(
                    conn,
                    path=row[0],
                    content_sha256=row[1],
                    streaminfo_md5=row[2],
                    checksum=row[3],
                    size_bytes=row[4],
                    mtime=row[5],
                    duration_s=row[6],
                    sample_rate=row[7],
                    bit_depth=row[8],
                    bitrate=row[9],
                    library=row[10],
                    zone=row[11],
                    download_source=row[12],
                    download_date=row[13],
                    mgmt_status=row[14],
                    metadata=metadata,
                    duration_ref_ms=row[16],
                    duration_ref_source=row[17],
                )
                if identity_id is not None:
                    linked += 1
            else:
                # Dry-run estimate: count rows with obvious identity hints.
                if metadata.get("isrc") or metadata.get("ISRC") or metadata.get(
                    "beatport_track_id"
                ):
                    linked += 1
            processed += 1

        if args.execute:
            conn.commit()

        mode = "EXECUTE" if args.execute else "DRY-RUN"
        print(f"{mode}: processed={processed} linked_estimate_or_rows={linked}")
        print(f"DB: {db_path}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
