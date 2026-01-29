"""Database read helpers for metadata enrichment."""

import json
import sqlite3
from typing import Optional, List, Any, Iterator

from dedupe.metadata.models.types import LocalFileInfo


def row_to_local_file_info(row: sqlite3.Row) -> LocalFileInfo:
    """Convert database row to LocalFileInfo."""
    # Parse metadata_json for tags
    metadata = {}
    if row["metadata_json"]:
        try:
            metadata = json.loads(row["metadata_json"])
        except json.JSONDecodeError:
            pass

    # Extract common tag fields
    # Tags from mutagen are often lists, take first element
    def get_tag(key: str) -> Optional[str]:
        val = metadata.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
        elif val:
            return str(val)
        return None

    def get_int_tag(key: str) -> Optional[int]:
        val = get_tag(key)
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return None

    return LocalFileInfo(
        path=row["path"],
        measured_duration_s=row["duration"],
        tag_artist=get_tag("artist") or get_tag("albumartist"),
        tag_title=get_tag("title"),
        tag_album=get_tag("album"),
        tag_isrc=get_tag("isrc"),
        tag_label=get_tag("label") or get_tag("organization"),
        tag_year=get_int_tag("date") or get_int_tag("year"),
        beatport_id=get_tag("beatport_track_id"),
        beatport_track_url=get_tag("beatport_track_url"),
        beatport_release_id=get_tag("beatport_release_id"),
        beatport_release_url=get_tag("beatport_release_url"),
    )


def get_eligible_files(
    db_path,
    path_pattern: Optional[str] = None,
    limit: Optional[int] = None,
    force: bool = False,
    retry_no_match: bool = False,
    zones: Optional[List[str]] = None,
) -> Iterator[LocalFileInfo]:
    """
    Query database for files eligible for enrichment.

    Eligible = healthy (flac_ok=1) AND not already enriched (unless force/retry)

    Args:
        path_pattern: Optional SQL LIKE pattern to filter paths
        limit: Maximum files to return
        force: If True, include ALL already-enriched files
        retry_no_match: If True, include files that previously had no match

    Yields:
        LocalFileInfo objects
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        query = """
            SELECT
                path, duration, metadata_json,
                enriched_at, canonical_isrc, zone
            FROM files
            WHERE flac_ok = 1
        """
        params: List[Any] = []

        if force:
            # Re-process everything
            pass
        elif retry_no_match:
            # Only retry files that had no match
            query += " AND (enriched_at IS NULL OR metadata_health_reason = 'no_provider_match')"
        else:
            # Skip all processed files
            query += " AND enriched_at IS NULL"

        if path_pattern:
            query += " AND path LIKE ?"
            params.append(path_pattern)

        if zones:
            placeholders = ",".join(["?"] * len(zones))
            query += f" AND zone IN ({placeholders})"
            params.extend([str(z).lower() for z in zones])

        query += " ORDER BY path"

        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor = conn.execute(query, params)

        for row in cursor:
            yield row_to_local_file_info(row)

    finally:
        conn.close()


def get_file_row(db_path, path: str) -> Optional[sqlite3.Row]:
    """Fetch a single file row by path."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT path, duration, metadata_json, enriched_at, canonical_isrc, flac_ok, metadata_health_reason "
            "FROM files WHERE path = ?",
            (path,),
        ).fetchone()
        return row
    finally:
        conn.close()


def get_file_info(db_path, path: str) -> Optional[LocalFileInfo]:
    """Fetch a single file by path and convert to LocalFileInfo."""
    row = get_file_row(db_path, path)
    if not row:
        return None
    return row_to_local_file_info(row)
