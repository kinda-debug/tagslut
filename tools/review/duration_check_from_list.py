#!/usr/bin/env python3
"""Run duration-check logic on an explicit list of file paths.

This mirrors tagslut index duration-check behavior but accepts a file list.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from mutagen.flac import FLAC

from tagslut.cli.commands._index_helpers import (
    duration_check_version,
    duration_status,
    duration_thresholds_from_config,
    extract_tag_value,
    lookup_duration_ref_ms,
    measure_duration_ms,
)
from tagslut.storage.schema import get_connection, init_db
from tagslut.utils.audit_log import append_jsonl, resolve_log_path
from tagslut.utils.db import resolve_db_path


def load_paths(path_file: Path) -> list[Path]:
    paths = [line.strip() for line in path_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [Path(p).expanduser().resolve() for p in paths]


def main() -> int:
    parser = argparse.ArgumentParser(description="Duration-check for explicit file list")
    parser.add_argument("path_list", type=Path, help="Text file with one absolute path per line")
    parser.add_argument("--db", type=Path, required=True, help="Database path")
    parser.add_argument("--execute", action="store_true", help="Write duration updates to DB")
    parser.add_argument("--dj-only", action="store_true", help="Mark checked files as DJ material")
    parser.add_argument("--source", default=None, help="Override source label for logging")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    file_paths = load_paths(args.path_list)
    if not file_paths:
        print("No files in list")
        return 0

    ok_max_ms, warn_max_ms = duration_thresholds_from_config()
    duration_version = duration_check_version(ok_max_ms, warn_max_ms)
    now_iso = datetime.now(timezone.utc).isoformat()

    resolution = resolve_db_path(args.db, purpose="write" if args.execute else "read", allow_create=bool(args.execute))
    db_path = resolution.path

    conn = get_connection(str(db_path), purpose="write" if args.execute else "read", allow_create=bool(args.execute))
    if args.execute:
        init_db(conn)

    updated = 0
    missing = 0
    errors = 0

    try:
        for i, file_path in enumerate(file_paths, start=1):
            try:
                row = conn.execute("SELECT path FROM files WHERE path = ?", (str(file_path),)).fetchone()
                if not row:
                    missing += 1
                    if args.verbose:
                        print(f"  [{i}/{len(file_paths)}] SKIP (not in DB) {file_path.name}")
                    continue

                audio = None
                try:
                    audio = FLAC(file_path)
                except Exception:
                    audio = None

                tags = audio.tags or {} if audio is not None else {}
                beatport_id = extract_tag_value(tags, ["BEATPORT_TRACK_ID", "BP_TRACK_ID", "beatport_track_id"])
                isrc = extract_tag_value(tags, ["ISRC", "TSRC"])

                duration_ref_ms, duration_ref_source, duration_ref_track_id = lookup_duration_ref_ms(
                    conn, beatport_id, isrc
                )
                duration_measured_ms = measure_duration_ms(file_path)
                duration_delta_ms = None
                if duration_measured_ms is not None and duration_ref_ms is not None:
                    duration_delta_ms = duration_measured_ms - duration_ref_ms
                duration_status_value = duration_status(duration_delta_ms, ok_max_ms, warn_max_ms)

                log_payload = {
                    "event": "duration_check",
                    "timestamp": now_iso,
                    "path": str(file_path),
                    "source": args.source,
                    "track_id": f"beatport:{beatport_id}" if beatport_id else (f"isrc:{isrc}" if isrc else None),
                    "is_dj_material": bool(args.dj_only),
                    "duration_ref_ms": duration_ref_ms,
                    "duration_measured_ms": duration_measured_ms,
                    "duration_delta_ms": duration_delta_ms,
                    "duration_status": duration_status_value,
                    "thresholds_ms": {"ok": ok_max_ms, "warn": warn_max_ms},
                    "check_version": duration_version,
                }
                append_jsonl(resolve_log_path("mgmt_duration"), log_payload)

                if args.dj_only and duration_status_value in ("warn", "fail", "unknown"):
                    anomaly_payload = {
                        "event": "duration_anomaly",
                        "timestamp": now_iso,
                        "path": str(file_path),
                        "track_id": log_payload["track_id"],
                        "is_dj_material": True,
                        "duration_status": duration_status_value,
                        "duration_ref_ms": duration_ref_ms,
                        "duration_measured_ms": duration_measured_ms,
                        "duration_delta_ms": duration_delta_ms,
                        "action": "blocked_promotion",
                    }
                    append_jsonl(resolve_log_path("mgmt_duration"), anomaly_payload)

                if args.execute:
                    conn.execute(
                        """
                        UPDATE files SET
                            is_dj_material = CASE WHEN ? THEN 1 ELSE is_dj_material END,
                            duration_ref_ms = ?,
                            duration_ref_source = ?,
                            duration_ref_track_id = ?,
                            duration_ref_updated_at = ?,
                            duration_measured_ms = ?,
                            duration_measured_at = ?,
                            duration_delta_ms = ?,
                            duration_status = ?,
                            duration_check_version = ?,
                            mgmt_status = CASE
                                WHEN ? AND ? IN ('warn','fail','unknown') THEN 'needs_review'
                                ELSE mgmt_status
                            END
                        WHERE path = ?
                        """,
                        (
                            1 if args.dj_only else 0,
                            duration_ref_ms,
                            duration_ref_source,
                            duration_ref_track_id,
                            now_iso if duration_ref_ms is not None else None,
                            duration_measured_ms,
                            now_iso if duration_measured_ms is not None else None,
                            duration_delta_ms,
                            duration_status_value,
                            duration_version,
                            1 if args.dj_only else 0,
                            duration_status_value,
                            str(file_path),
                        ),
                    )

                if args.verbose or i % 50 == 0 or i == len(file_paths):
                    print(f"  [{i}/{len(file_paths)}] {file_path.name}")
                updated += 1

            except Exception as e:
                errors += 1
                print(f"  ERROR: {file_path.name}: {e}")

        if args.execute:
            conn.commit()

    finally:
        conn.close()

    print("")
    print("=" * 50)
    print("DURATION CHECK RESULTS")
    print("=" * 50)
    print(f"  Total:        {len(file_paths):>6}")
    print(f"  Updated:      {updated:>6}")
    print(f"  Missing DB:   {missing:>6}")
    print(f"  Errors:       {errors:>6}  {'⚠' if errors > 0 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
