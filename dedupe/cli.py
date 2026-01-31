"""CLI module to inspect the track hub directly.

Usage:
    python -m dedupe.cli track-by-path /path/to/file.flac --db /path/to/music.db
    python -m dedupe.cli track-by-key "isrc:USRC12345678" --db /path/to/music.db
    python -m dedupe.cli list-files-for-key "isrc:USRC12345678" --db /path/to/music.db
    python -m dedupe.cli find-by-isrc USRC12345678 --db /path/to/music.db
    python -m dedupe.cli find-by-provider spotify 4iV5W9uYEdYUVa79Axb7Rh --db /path/to/music.db

Commands:
    track-by-path      Look up a file by its path and show linked track hub data.
    track-by-key       Look up a track directly by its library_track_key.
    list-files-for-key List all files linked to a given library_track_key.
    find-by-isrc       Find a track by ISRC and display its hub data.
    find-by-provider   Find a track by provider service and track ID.

Both commands display:
    - The files row (for track-by-path only)
    - The library_tracks row for the linked key
    - All library_track_sources rows for that key
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def _connect_db(db_path: str) -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database."""
    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _print_section(title: str) -> None:
    """Print a section header."""
    print()
    print(f"{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def _print_row(row: sqlite3.Row, fields: list[str], indent: int = 2) -> None:
    """Print selected fields from a row."""
    prefix = " " * indent
    max_label = max(len(f) for f in fields) if fields else 0
    for field in fields:
        value = row[field] if field in row.keys() else None
        label = field.ljust(max_label)
        print(f"{prefix}{label}: {value}")


def _show_files_row(conn: sqlite3.Connection, path: str) -> str | None:
    """Look up and display the files row for a given path.
    
    Returns the library_track_key if found, else None.
    """
    cursor = conn.execute(
        """
        SELECT path, library_track_key, canonical_isrc, canonical_duration,
               canonical_duration_source, metadata_health, metadata_health_reason,
               enrichment_providers, enrichment_confidence
        FROM files
        WHERE path = ?
        """,
        (path,),
    )
    row = cursor.fetchone()
    
    if row is None:
        print(f"Error: No file found with path: {path}", file=sys.stderr)
        return None
    
    _print_section("FILES ROW")
    fields = [
        "path",
        "library_track_key",
        "canonical_isrc",
        "canonical_duration",
        "canonical_duration_source",
        "metadata_health",
        "metadata_health_reason",
        "enrichment_providers",
        "enrichment_confidence",
    ]
    _print_row(row, fields)
    
    return row["library_track_key"]


def _show_library_track(conn: sqlite3.Connection, key: str) -> bool:
    """Display the library_tracks row for a given key.
    
    Returns True if found, False otherwise.
    """
    cursor = conn.execute(
        """
        SELECT library_track_key, title, artist, album, duration_ms, isrc,
               release_date, explicit, best_cover_url, genre, bpm, musical_key,
               label, updated_at
        FROM library_tracks
        WHERE library_track_key = ?
        """,
        (key,),
    )
    row = cursor.fetchone()
    
    if row is None:
        print(f"\n  (No library_tracks row found for key: {key})")
        return False
    
    _print_section("LIBRARY_TRACKS")
    fields = [
        "library_track_key",
        "title",
        "artist",
        "album",
        "duration_ms",
        "isrc",
        "release_date",
        "explicit",
        "best_cover_url",
        "genre",
        "bpm",
        "musical_key",
        "label",
        "updated_at",
    ]
    _print_row(row, fields)
    return True


def _show_library_track_sources(conn: sqlite3.Connection, key: str) -> None:
    """Display all library_track_sources rows for a given key."""
    cursor = conn.execute(
        """
        SELECT service, service_track_id, url, duration_ms, isrc, album_art_url,
               genre, bpm, musical_key, album_title, artist_name, track_number,
               disc_number, match_confidence, fetched_at, metadata_json
        FROM library_track_sources
        WHERE library_track_key = ?
        ORDER BY service, service_track_id
        """,
        (key,),
    )
    rows = cursor.fetchall()
    
    _print_section(f"LIBRARY_TRACK_SOURCES ({len(rows)} row(s))")
    
    if not rows:
        print("  (No source rows found)")
        return
    
    for i, row in enumerate(rows, 1):
        print(f"\n  --- Source #{i} ---")
        has_json = row["metadata_json"] is not None
        fields = [
            "service",
            "service_track_id",
            "url",
            "duration_ms",
            "isrc",
            "genre",
            "bpm",
            "musical_key",
            "album_title",
            "artist_name",
            "track_number",
            "disc_number",
            "match_confidence",
            "fetched_at",
        ]
        _print_row(row, fields, indent=4)
        print(f"    {'metadata_json'.ljust(16)}: {'[present]' if has_json else '[absent]'}")


def cmd_track_by_path(args: argparse.Namespace) -> None:
    """Handle the track-by-path command."""
    conn = _connect_db(args.db)
    
    try:
        key = _show_files_row(conn, args.path)
        
        if key is None:
            sys.exit(1)
        
        if not key or key.strip() == "":
            print("\n  Note: library_track_key is NULL or empty for this file.")
            print("  The file has not been linked to the track hub yet.")
            return
        
        _show_library_track(conn, key)
        _show_library_track_sources(conn, key)
    finally:
        conn.close()


def _show_track_hub(conn: sqlite3.Connection, key: str) -> bool:
    """Display library_tracks and library_track_sources for a given key.
    
    Returns True if the library_tracks row was found, False otherwise.
    """
    found = _show_library_track(conn, key)
    _show_library_track_sources(conn, key)
    return found


def cmd_track_by_key(args: argparse.Namespace) -> None:
    """Handle the track-by-key command."""
    conn = _connect_db(args.db)
    
    try:
        key = args.key
        print(f"Looking up library_track_key: {key}")
        
        found = _show_library_track(conn, key)
        if not found:
            print("\n  No track found with this key.", file=sys.stderr)
            sys.exit(1)
        
        _show_library_track_sources(conn, key)
    finally:
        conn.close()


def cmd_list_files_for_key(args: argparse.Namespace) -> None:
    """Handle the list-files-for-key command."""
    conn = _connect_db(args.db)
    
    try:
        key = args.key
        cursor = conn.execute(
            """
            SELECT path, canonical_duration, metadata_health, metadata_health_reason
            FROM files
            WHERE library_track_key = ?
            ORDER BY path
            """,
            (key,),
        )
        rows = cursor.fetchall()
        
        if not rows:
            print(f"No files found for library_track_key: {key}")
            return
        
        _print_section(f"FILES FOR KEY: {key}")
        print(f"  Found {len(rows)} file(s):\n")
        
        for i, row in enumerate(rows, 1):
            print(f"  [{i}] {row['path']}")
            if row["canonical_duration"] is not None:
                print(f"      duration: {row['canonical_duration']}")
            if row["metadata_health"]:
                print(f"      health: {row['metadata_health']}")
            if row["metadata_health_reason"]:
                print(f"      health_reason: {row['metadata_health_reason']}")
    finally:
        conn.close()


def cmd_find_by_isrc(args: argparse.Namespace) -> None:
    """Handle the find-by-isrc command."""
    conn = _connect_db(args.db)
    
    try:
        isrc = args.isrc.strip().upper()
        key = f"isrc:{isrc}"
        print(f"Derived library_track_key: {key}")
        
        found = _show_track_hub(conn, key)
        if not found:
            print(f"\n  No track found for ISRC: {isrc}", file=sys.stderr)
            sys.exit(1)
    finally:
        conn.close()


def cmd_find_by_provider(args: argparse.Namespace) -> None:
    """Handle the find-by-provider command."""
    conn = _connect_db(args.db)
    
    try:
        service = args.service.lower()
        track_id = args.track_id.strip()
        
        cursor = conn.execute(
            """
            SELECT DISTINCT library_track_key, service, service_track_id, fetched_at
            FROM library_track_sources
            WHERE service = ? AND service_track_id = ?
            """,
            (service, track_id),
        )
        rows = cursor.fetchall()
        
        if not rows:
            print(f"No source found for service={service}, track_id={track_id}")
            return
        
        print(f"Found {len(rows)} source row(s) for {service}:{track_id}\n")
        
        seen_keys = set()
        for row in rows:
            key = row["library_track_key"]
            print(f"  Source: service={row['service']}, service_track_id={row['service_track_id']}, fetched_at={row['fetched_at']}")
            print(f"  library_track_key: {key}")
            
            if key and key not in seen_keys:
                seen_keys.add(key)
                _show_track_hub(conn, key)
            print()
    finally:
        conn.close()


def cmd_diagnose_duplicates(args: argparse.Namespace) -> None:
    """Handle the diagnose-duplicates command.
    
    Find library_track_key values with multiple files and display diagnostic info.
    """
    conn = _connect_db(args.db)
    
    try:
        min_files = args.min_files
        limit = args.limit
        
        # Step 1: Find candidate keys with multiple files
        cursor = conn.execute(
            """
            SELECT library_track_key, COUNT(*) as file_count
            FROM files
            WHERE library_track_key IS NOT NULL AND library_track_key != ''
            GROUP BY library_track_key
            HAVING file_count >= ?
            ORDER BY file_count DESC
            LIMIT ?;
            """,
            (min_files, limit),
        )
        candidates = cursor.fetchall()
        
        if not candidates:
            print(f"No library_track_key values found with >= {min_files} files.")
            return
        
        print(f"Found {len(candidates)} key(s) with >= {min_files} files:\n")
        
        # Step 2 & 3: For each key, fetch and display details
        for row in candidates:
            key = row["library_track_key"]
            file_count = row["file_count"]
            
            # Fetch provider count
            provider_cursor = conn.execute(
                """
                SELECT COUNT(*) as provider_count
                FROM library_track_sources
                WHERE library_track_key = ?
                """,
                (key,),
            )
            provider_row = provider_cursor.fetchone()
            provider_count = provider_row["provider_count"] if provider_row else 0
            
            print(f"=== library_track_key={key} (files={file_count}, providers={provider_count}) ===")
            
            # Fetch canonical track info
            track_cursor = conn.execute(
                """
                SELECT title, artist, album, duration_ms, isrc, explicit, genre
                FROM library_tracks
                WHERE library_track_key = ?
                """,
                (key,),
            )
            track_row = track_cursor.fetchone()
            
            if track_row:
                artist = track_row["artist"] or "?"
                title = track_row["title"] or "?"
                album = track_row["album"] or "?"
                duration_ms = track_row["duration_ms"]
                isrc = track_row["isrc"] or "?"
                explicit = track_row["explicit"]
                genre = track_row["genre"] or "?"
                
                explicit_str = str(explicit) if explicit is not None else "?"
                duration_str = str(duration_ms) if duration_ms is not None else "?"
                
                print(f"Canonical: {artist} - {title} ({album}), duration_ms={duration_str}, isrc={isrc}, explicit={explicit_str}, genre={genre}")
            else:
                print("Canonical: (no library_tracks row)")
            
            # Fetch provider sources
            sources_cursor = conn.execute(
                """
                SELECT service, service_track_id, match_confidence
                FROM library_track_sources
                WHERE library_track_key = ?
                ORDER BY service, service_track_id
                """,
                (key,),
            )
            sources = sources_cursor.fetchall()
            
            if sources:
                print("Providers:")
                for src in sources:
                    service = src["service"] or "?"
                    track_id = src["service_track_id"] or "?"
                    confidence = src["match_confidence"] or "?"
                    print(f"  - {service} {track_id} (match={confidence})")
            else:
                print("Providers: (none)")
            
            # Fetch files
            files_cursor = conn.execute(
                """
                SELECT path, metadata_health, metadata_health_reason
                FROM files
                WHERE library_track_key = ?
                ORDER BY path
                """,
                (key,),
            )
            files = files_cursor.fetchall()
            
            print("Files:")
            for f in files:
                path = f["path"]
                health = f["metadata_health"] or "?"
                reason = f["metadata_health_reason"]
                
                if reason:
                    print(f"  - {path} [health={health} reason={reason}]")
                else:
                    print(f"  - {path} [health={health}]")
            
            print()  # Blank line between keys
    finally:
        conn.close()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="dedupe.cli",
        description="Inspect the track hub (library_tracks, library_track_sources) directly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m dedupe.cli track-by-path /Music/Artist/Track.flac --db ./music.db
    python -m dedupe.cli track-by-key "isrc:USRC12345678" --db ./music.db
    python -m dedupe.cli track-by-key "spotify:4iV5W9uYEdYUVa79Axb7Rh" --db ./music.db
    python -m dedupe.cli list-files-for-key "isrc:USRC12345678" --db ./music.db
    python -m dedupe.cli find-by-isrc USRC12345678 --db ./music.db
    python -m dedupe.cli find-by-provider spotify 4iV5W9uYEdYUVa79Axb7Rh --db ./music.db
    python -m dedupe.cli diagnose-duplicates --db ./music.db --min-files 2 --limit 50
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # track-by-path subcommand
    parser_path = subparsers.add_parser(
        "track-by-path",
        help="Look up a file by its path and show linked track hub data.",
        description="Query the files table by path, then display the linked library_tracks and library_track_sources.",
    )
    parser_path.add_argument(
        "path",
        help="The file path (as stored in files.path, typically absolute).",
    )
    parser_path.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_path.set_defaults(func=cmd_track_by_path)
    
    # track-by-key subcommand
    parser_key = subparsers.add_parser(
        "track-by-key",
        help="Look up a track directly by its library_track_key.",
        description="Query library_tracks and library_track_sources by the given key.",
    )
    parser_key.add_argument(
        "key",
        help="The library_track_key (e.g., 'isrc:USRC12345678', 'spotify:4iV5W9uYEdYUVa79Axb7Rh').",
    )
    parser_key.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_key.set_defaults(func=cmd_track_by_key)
    
    # list-files-for-key subcommand
    parser_list_files = subparsers.add_parser(
        "list-files-for-key",
        help="List all files linked to a given library_track_key.",
        description="Query the files table for all rows with the given library_track_key.",
    )
    parser_list_files.add_argument(
        "key",
        help="The library_track_key to look up.",
    )
    parser_list_files.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_list_files.set_defaults(func=cmd_list_files_for_key)
    
    # find-by-isrc subcommand
    parser_isrc = subparsers.add_parser(
        "find-by-isrc",
        help="Find a track by ISRC and display its hub data.",
        description="Construct library_track_key from ISRC and display library_tracks and library_track_sources.",
    )
    parser_isrc.add_argument(
        "isrc",
        help="The ISRC (without 'isrc:' prefix, e.g., 'USRC12345678').",
    )
    parser_isrc.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_isrc.set_defaults(func=cmd_find_by_isrc)
    
    # find-by-provider subcommand
    parser_provider = subparsers.add_parser(
        "find-by-provider",
        help="Find a track by provider service and track ID.",
        description="Query library_track_sources by service and service_track_id, then display the linked track hub.",
    )
    parser_provider.add_argument(
        "service",
        help="The provider service name (e.g., 'beatport', 'spotify', 'qobuz', 'tidal', 'itunes').",
    )
    parser_provider.add_argument(
        "track_id",
        help="The service-specific track ID.",
    )
    parser_provider.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_provider.set_defaults(func=cmd_find_by_provider)
    
    # diagnose-duplicates subcommand
    parser_duplicates = subparsers.add_parser(
        "diagnose-duplicates",
        help="Find library_track_key values with multiple files (potential duplicates).",
        description="Query for library_track_key values that have multiple files linked, "
                    "displaying canonical track info, provider sources, and file paths.",
    )
    parser_duplicates.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_duplicates.add_argument(
        "--min-files",
        type=int,
        default=2,
        help="Minimum number of files per key to report (default: 2).",
    )
    parser_duplicates.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of keys to display (default: 100).",
    )
    parser_duplicates.set_defaults(func=cmd_diagnose_duplicates)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
