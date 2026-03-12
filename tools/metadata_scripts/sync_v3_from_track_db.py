#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tagslut.metadata.track_db_sync import PROVIDER_NAME, sync_v3_from_track_db
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enrich music_v3.db canonical metadata from a Rekordbox-style SQLite Track table."
    )
    parser.add_argument("--db", help="Path to music_v3.db")
    parser.add_argument("--donor-db", required=True, help="Path to external SQLite DB with Track table")
    parser.add_argument(
        "--donor-location-like",
        default="/Volumes/MUSIC/DJ_LIBRARY/%",
        help="SQL LIKE filter for donor Track.location rows",
    )
    parser.add_argument(
        "--match-field",
        default="dj_pool_path",
        choices=("dj_pool_path", "path"),
        help="files column to match against donor Track.location",
    )
    parser.add_argument(
        "--match-mode",
        default="exact_path",
        choices=("exact_path", "normalized_taa", "both"),
        help="How to match donor Track rows to working DB rows",
    )
    parser.add_argument(
        "--provider-name",
        default=PROVIDER_NAME,
        help="Provider label to append to files.enrichment_providers",
    )
    parser.add_argument("--out-dir", default="", help="Directory for summary/report artifacts")
    parser.add_argument("--execute", action="store_true", help="Write updates to the working DB")
    args = parser.parse_args()

    purpose = "write" if args.execute else "read"
    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose=purpose, source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    work_db_path = db_resolution.path
    donor_db_path = Path(args.donor_db).expanduser().resolve()
    if not donor_db_path.exists():
        raise SystemExit(f"ERROR: donor DB not found: {donor_db_path}")

    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else REPO_ROOT / "artifacts" / f"track_db_sync_{_timestamp()}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(work_db_path), timeout=60.0) as conn, sqlite3.connect(
        str(donor_db_path), timeout=60.0
    ) as donor_conn:
        conn.execute("PRAGMA busy_timeout = 60000")
        donor_conn.execute("PRAGMA busy_timeout = 60000")
        result = sync_v3_from_track_db(
            conn,
            donor_conn,
            donor_location_like=args.donor_location_like,
            match_field=args.match_field,
            match_mode=args.match_mode,
            provider_name=args.provider_name,
            execute=args.execute,
        )

    files_csv = out_dir / "file_updates.csv"
    with files_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "dj_pool_path", "match_mode", "applied_fields"])
        writer.writeheader()
        for row in result.file_updates:
            writer.writerow(
                {
                    "path": row.path,
                    "dj_pool_path": row.dj_pool_path,
                    "match_mode": row.match_mode,
                    "applied_fields": ";".join(row.applied_fields),
                }
            )

    identities_csv = out_dir / "identity_updates.csv"
    with identities_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["identity_id", "applied_fields"])
        writer.writeheader()
        for row in result.identity_updates:
            writer.writerow(
                {
                    "identity_id": row.identity_id,
                    "applied_fields": ";".join(row.applied_fields),
                }
            )

    summary = {
        "work_db_path": str(work_db_path),
        "donor_db_path": str(donor_db_path),
        "donor_location_like": args.donor_location_like,
        "match_field": args.match_field,
        "match_mode": args.match_mode,
        "execute": bool(args.execute),
        "donor_tracks": result.donor_tracks,
        "files_considered": result.files_considered,
        "matched_files": result.matched_files,
        "file_rows_updated": result.file_rows_updated,
        "file_fields_written": result.file_fields_written,
        "identity_rows_updated": result.identity_rows_updated,
        "identity_fields_written": result.identity_fields_written,
        "identity_field_conflicts": result.identity_field_conflicts,
        "file_field_conflicts": result.file_field_conflicts,
        "match_mode_counts": result.match_mode_counts,
        "file_updates_csv": str(files_csv),
        "identity_updates_csv": str(identities_csv),
    }
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
