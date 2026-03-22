from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _norm_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _to_int(value: Any) -> int | None:
    text = _norm_text(value)
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def _track_key(
    *,
    service: str,
    service_track_id: str,
    isrc: str | None,
) -> str:
    isrc_text = _norm_text(isrc).upper()
    if isrc_text:
        return f"isrc:{isrc_text}"
    return f"{service}:{_norm_text(service_track_id)}"


@dataclass(frozen=True)
class RefreshStats:
    tracks_seen: int = 0
    tracks_written: int = 0
    tracks_skipped_missing_id: int = 0
    hub_tables_missing: int = 0


def refresh_track_hub_from_tracks_csv(
    *,
    db_path: Path,
    tracks_csv: Path,
) -> tuple[RefreshStats, Path | None]:
    stats = RefreshStats()
    db_path = db_path.expanduser().resolve()
    tracks_csv = tracks_csv.expanduser().resolve()
    if not tracks_csv.exists():
        raise FileNotFoundError(str(tracks_csv))

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "library_tracks") or not _table_exists(conn, "library_track_sources"):
            return RefreshStats(hub_tables_missing=1), None

        conn.execute("BEGIN IMMEDIATE")
        tracks_seen = 0
        tracks_written = 0
        skipped_missing_id = 0

        with tracks_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                tracks_seen += 1
                service = _norm_text(row.get("domain")) or "unknown"
                service_track_id = _norm_text(row.get("track_id"))
                if not service_track_id:
                    skipped_missing_id += 1
                    continue

                title = _norm_text(row.get("title")) or None
                artist = _norm_text(row.get("artist")) or None
                album = _norm_text(row.get("album")) or None
                isrc = _norm_text(row.get("isrc")) or None
                duration_ms = _to_int(row.get("duration_ms"))
                url = _norm_text(row.get("normalized_link") or row.get("source_link")) or None

                key = _track_key(service=service, service_track_id=service_track_id, isrc=isrc)
                match_confidence = "exact"

                conn.execute(
                    """
                    INSERT INTO library_tracks (
                        library_track_key,
                        title,
                        artist,
                        album,
                        duration_ms,
                        isrc,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(library_track_key) DO UPDATE SET
                        title = COALESCE(excluded.title, library_tracks.title),
                        artist = COALESCE(excluded.artist, library_tracks.artist),
                        album = COALESCE(excluded.album, library_tracks.album),
                        duration_ms = COALESCE(excluded.duration_ms, library_tracks.duration_ms),
                        isrc = COALESCE(excluded.isrc, library_tracks.isrc),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, title, artist, album, duration_ms, isrc),
                )

                # Idempotent provider snapshot: delete then insert.
                conn.execute(
                    """
                    DELETE FROM library_track_sources
                    WHERE library_track_key = ? AND service = ? AND service_track_id = ?
                    """,
                    (key, service, service_track_id),
                )
                conn.execute(
                    """
                    INSERT INTO library_track_sources (
                        library_track_key,
                        service,
                        service_track_id,
                        url,
                        metadata_json,
                        duration_ms,
                        isrc,
                        album_title,
                        artist_name,
                        match_confidence,
                        fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        key,
                        service,
                        service_track_id,
                        url,
                        json.dumps(dict(row), ensure_ascii=False, sort_keys=True),
                        duration_ms,
                        isrc,
                        album,
                        artist,
                        match_confidence,
                    ),
                )

                tracks_written += 1

        conn.commit()

        summary_path = tracks_csv.parent / f"url_metadata_refresh_summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        payload = {
            "tracks_csv": str(tracks_csv),
            "db_path": str(db_path),
            "tracks_seen": tracks_seen,
            "tracks_written": tracks_written,
            "tracks_skipped_missing_id": skipped_missing_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        return (
            RefreshStats(
                tracks_seen=tracks_seen,
                tracks_written=tracks_written,
                tracks_skipped_missing_id=skipped_missing_id,
                hub_tables_missing=0,
            ),
            summary_path,
        )
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh track-hub provider snapshots from an extracted tracks CSV.")
    ap.add_argument("--db", required=True, help="Path to SQLite DB")
    ap.add_argument("--tracks-csv", required=True, help="precheck_tracks_extracted_*.csv file")
    ap.add_argument("--source-url", help="Original input URL (for logging only)")
    ap.add_argument("--out-dir", help="Output directory (defaults to tracks-csv parent)")
    args = ap.parse_args()

    db_path = Path(args.db)
    tracks_csv = Path(args.tracks_csv)

    # Allow overriding output directory by copying the CSV path parent into out_dir for summary file placement.
    if args.out_dir:
        out_dir = Path(args.out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        stats, summary_path = refresh_track_hub_from_tracks_csv(db_path=db_path, tracks_csv=tracks_csv)
        if summary_path and summary_path.parent != out_dir:
            moved = out_dir / summary_path.name
            moved.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
            summary_path = moved
    else:
        stats, summary_path = refresh_track_hub_from_tracks_csv(db_path=db_path, tracks_csv=tracks_csv)

    source_url = (args.source_url or "").strip()
    if source_url:
        print(f"Source URL: {source_url}")
    if stats.hub_tables_missing:
        print("Track hub tables missing; skipping refresh.")
        return 0
    print(
        "Metadata refresh complete:"
        f" tracks_seen={stats.tracks_seen}"
        f" tracks_written={stats.tracks_written}"
        f" skipped_missing_id={stats.tracks_skipped_missing_id}"
        + (f" summary={summary_path}" if summary_path else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
