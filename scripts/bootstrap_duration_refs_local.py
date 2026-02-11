#!/usr/bin/env python3
"""
Bootstrap duration reference rows from local DB metadata only.

This script does not call any remote provider APIs and does not require tokens.
It fills `track_duration_refs` from:
1) `library_track_sources` (service snapshots already in your DB)
2) `library_tracks` ISRC + duration (optional)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ISRC_SPLIT_RE = re.compile(r"[;,/\\]|\s+")


@dataclass
class CoverageStats:
    total_files: int = 0
    files_with_bp_tag: int = 0
    files_with_isrc_tag: int = 0
    files_with_match: int = 0


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _normalize_isrc(value) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().upper()
    if not raw:
        return None
    first_token = ISRC_SPLIT_RE.split(raw)[0].strip()
    return first_token or None


def _extract_all_isrc_tokens(value) -> list[str]:
    out: list[str] = []
    if value is None:
        return out
    values = value if isinstance(value, list) else [value]
    for part in values:
        for token in ISRC_SPLIT_RE.split(str(part).strip().upper()):
            token = token.strip()
            if token:
                out.append(token)
    # stable de-duplication
    seen = set()
    unique = []
    for token in out:
        if token in seen:
            continue
        seen.add(token)
        unique.append(token)
    return unique


def _parse_length_ms(value) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Accept integer seconds
    if raw.isdigit():
        sec = int(raw)
        if 30 <= sec <= 3600:
            return sec * 1000
        return None

    # Accept mm:ss
    if re.fullmatch(r"\d{1,2}:\d{2}", raw):
        mins, secs = raw.split(":")
        total = int(mins) * 60 + int(secs)
        if 30 <= total <= 3600:
            return total * 1000
    return None


def _extract_ids(metadata_json: str) -> tuple[str | None, list[str], int | None]:
    try:
        payload = json.loads(metadata_json or "{}")
    except Exception:
        payload = {}

    beatport_id = _first(
        payload.get("beatport_track_id")
        or payload.get("BEATPORT_TRACK_ID")
        or payload.get("bp_track_id")
        or payload.get("BP_TRACK_ID")
    )
    beatport_id = str(beatport_id).strip() if beatport_id is not None else None
    if beatport_id == "":
        beatport_id = None

    isrc_raw = payload.get("isrc") or payload.get("ISRC") or payload.get("tsrc") or payload.get("TSRC")
    isrc_tokens = _extract_all_isrc_tokens(isrc_raw)

    length_raw = payload.get("length") or payload.get("LENGTH") or payload.get("_TIME_CHECK")
    if isinstance(length_raw, list):
        length_raw = _first(length_raw)
    length_ms = _parse_length_ms(length_raw)
    return beatport_id, isrc_tokens, length_ms


def _median_int(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def build_ref_maps(
    conn: sqlite3.Connection,
    services: list[str],
    include_library_tracks: bool,
) -> tuple[dict[str, int], dict[str, int]]:
    if not services:
        raise ValueError("services must not be empty")

    placeholders = ",".join("?" for _ in services)
    rows = conn.execute(
        f"""
        SELECT service, service_track_id, isrc, duration_ms
        FROM library_track_sources
        WHERE duration_ms IS NOT NULL
          AND service IN ({placeholders})
        """,
        tuple(services),
    )

    beatport_buckets: dict[str, list[int]] = {}
    isrc_buckets: dict[str, list[int]] = {}

    for row in rows:
        service = str(row["service"])
        duration_ms = int(row["duration_ms"])

        if service == "beatport":
            service_track_id = row["service_track_id"]
            if service_track_id is not None:
                ref_id = str(service_track_id).strip()
                if ref_id:
                    beatport_buckets.setdefault(ref_id, []).append(duration_ms)

        isrc = _normalize_isrc(row["isrc"])
        if isrc:
            isrc_buckets.setdefault(isrc, []).append(duration_ms)

    if include_library_tracks:
        for row in conn.execute(
            """
            SELECT isrc, duration_ms
            FROM library_tracks
            WHERE isrc IS NOT NULL
              AND duration_ms IS NOT NULL
            """
        ):
            isrc = _normalize_isrc(row["isrc"])
            if not isrc:
                continue
            isrc_buckets.setdefault(isrc, []).append(int(row["duration_ms"]))

    beatport_refs = {ref_id: _median_int(values) for ref_id, values in beatport_buckets.items()}
    isrc_refs = {ref_id: _median_int(values) for ref_id, values in isrc_buckets.items()}
    return beatport_refs, isrc_refs


def build_tag_length_ref_maps(
    conn: sqlite3.Connection,
    path_like: str,
) -> tuple[dict[str, int], dict[str, int]]:
    beatport_buckets: dict[str, list[int]] = {}
    isrc_buckets: dict[str, list[int]] = {}

    rows = conn.execute("SELECT metadata_json FROM files WHERE path LIKE ?", (path_like,))
    for row in rows:
        beatport_id, isrc_tokens, length_ms = _extract_ids(row["metadata_json"])
        if length_ms is None:
            continue

        if beatport_id:
            beatport_buckets.setdefault(beatport_id, []).append(length_ms)
        for token in isrc_tokens:
            isrc_buckets.setdefault(token, []).append(length_ms)

    beatport_refs = {ref_id: _median_int(values) for ref_id, values in beatport_buckets.items()}
    isrc_refs = {ref_id: _median_int(values) for ref_id, values in isrc_buckets.items()}
    return beatport_refs, isrc_refs


def merge_ref_maps(base: dict[str, int], extra: dict[str, int]) -> dict[str, int]:
    merged = dict(base)
    for key, duration_ms in extra.items():
        if key not in merged:
            merged[key] = duration_ms
    return merged


def estimate_coverage(
    conn: sqlite3.Connection,
    path_like: str,
    beatport_refs: dict[str, int],
    isrc_refs: dict[str, int],
) -> CoverageStats:
    stats = CoverageStats()
    rows = conn.execute("SELECT metadata_json FROM files WHERE path LIKE ?", (path_like,))
    for row in rows:
        stats.total_files += 1
        beatport_id, isrc_tokens, _length_ms = _extract_ids(row["metadata_json"])
        if beatport_id:
            stats.files_with_bp_tag += 1
        if isrc_tokens:
            stats.files_with_isrc_tag += 1
        isrc_hit = any(token in isrc_refs for token in isrc_tokens)
        if (beatport_id and beatport_id in beatport_refs) or isrc_hit:
            stats.files_with_match += 1
    return stats


def write_refs(
    conn: sqlite3.Connection,
    beatport_refs: dict[str, int],
    isrc_refs: dict[str, int],
    source_label: str,
) -> tuple[int, int, int]:
    inserted = 0
    updated = 0
    unchanged = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    def upsert_ref(ref_id: str, ref_type: str, duration_ms: int) -> None:
        nonlocal inserted, updated, unchanged
        existing = conn.execute(
            "SELECT duration_ref_ms, ref_source FROM track_duration_refs WHERE ref_id = ?",
            (ref_id,),
        ).fetchone()

        if existing and int(existing["duration_ref_ms"]) == duration_ms and existing["ref_source"] == source_label:
            unchanged += 1
            return

        conn.execute(
            """
            INSERT OR REPLACE INTO track_duration_refs
                (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ref_id, ref_type, duration_ms, source_label, now_iso),
        )

        if existing is None:
            inserted += 1
        else:
            updated += 1

    for ref_id, duration_ms in beatport_refs.items():
        upsert_ref(ref_id, "beatport_id", duration_ms)
    for ref_id, duration_ms in isrc_refs.items():
        upsert_ref(ref_id, "isrc", duration_ms)

    return inserted, updated, unchanged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap track_duration_refs from local DB state only (no tokens)."
    )
    parser.add_argument("--db", type=Path, required=True, help="Path to SQLite DB.")
    parser.add_argument(
        "--services",
        default="beatport,spotify,tidal",
        help="Comma-separated services to use from library_track_sources (default: beatport,spotify,tidal).",
    )
    parser.add_argument(
        "--path-like",
        default="/Volumes/MUSIC/LIBRARY/%",
        help="LIKE pattern for file coverage estimate (default: /Volumes/MUSIC/LIBRARY/%%).",
    )
    parser.add_argument(
        "--no-library-tracks",
        action="store_true",
        help="Do not use library_tracks isrc/duration rows when building refs.",
    )
    parser.add_argument(
        "--source-label",
        default="local_bootstrap",
        help="ref_source label written into track_duration_refs.",
    )
    parser.add_argument(
        "--include-tag-length",
        action="store_true",
        help="Also build refs from embedded file tags (length/_TIME_CHECK + Beatport/ISRC ids).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write into track_duration_refs (default is dry-run summary).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    services = [part.strip().lower() for part in args.services.split(",") if part.strip()]
    if not services:
        raise SystemExit("No services selected. Pass --services with at least one value.")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        beatport_refs, isrc_refs = build_ref_maps(
            conn=conn,
            services=services,
            include_library_tracks=not args.no_library_tracks,
        )
        base_bp_count = len(beatport_refs)
        base_isrc_count = len(isrc_refs)

        if args.include_tag_length:
            tag_bp_refs, tag_isrc_refs = build_tag_length_ref_maps(conn=conn, path_like=args.path_like)
            beatport_refs = merge_ref_maps(beatport_refs, tag_bp_refs)
            isrc_refs = merge_ref_maps(isrc_refs, tag_isrc_refs)
        else:
            tag_bp_refs = {}
            tag_isrc_refs = {}

        coverage = estimate_coverage(
            conn=conn,
            path_like=args.path_like,
            beatport_refs=beatport_refs,
            isrc_refs=isrc_refs,
        )

        print(f"DB: {db_path}")
        print(f"Services: {', '.join(services)}")
        print(f"Include library_tracks: {not args.no_library_tracks}")
        print(f"Include embedded tag length refs: {args.include_tag_length}")
        if args.include_tag_length:
            print(f"Added Beatport refs from tags: {len(beatport_refs) - base_bp_count}")
            print(f"Added ISRC refs from tags: {len(isrc_refs) - base_isrc_count}")
        print(f"Beatport ID refs: {len(beatport_refs)}")
        print(f"ISRC refs: {len(isrc_refs)}")
        print(f"Coverage pattern: {args.path_like}")
        print(f"Files scanned: {coverage.total_files}")
        print(f"Files with beatport tag: {coverage.files_with_bp_tag}")
        print(f"Files with isrc tag: {coverage.files_with_isrc_tag}")
        pct = (coverage.files_with_match / coverage.total_files * 100.0) if coverage.total_files else 0.0
        print(f"Files with at least one local duration match: {coverage.files_with_match} ({pct:.2f}%)")

        if not args.write:
            print("Dry-run complete. Use --write to persist track_duration_refs.")
            return 0

        inserted, updated, unchanged = write_refs(
            conn=conn,
            beatport_refs=beatport_refs,
            isrc_refs=isrc_refs,
            source_label=args.source_label,
        )
        conn.commit()
        print("Write complete:")
        print(f"  Inserted: {inserted}")
        print(f"  Updated: {updated}")
        print(f"  Unchanged: {unchanged}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
