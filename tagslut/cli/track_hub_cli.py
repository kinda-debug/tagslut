"""CLI module to inspect the track hub directly.

Usage:
    python -m tagslut.cli.track_hub_cli track-by-path /path/to/file.flac --db /path/to/music.db
    python -m tagslut.cli.track_hub_cli track-by-key "isrc:USRC12345678" --db /path/to/music.db
    python -m tagslut.cli.track_hub_cli list-files-for-key "isrc:USRC12345678" --db /path/to/music.db
    python -m tagslut.cli.track_hub_cli find-by-isrc USRC12345678 --db /path/to/music.db
    python -m tagslut.cli.track_hub_cli find-by-provider spotify 4iV5W9uYEdYUVa79Axb7Rh --db /path/to/music.db

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

Note: This module lives under tagslut/cli/ alongside the main
Click-based CLI under tagslut/cli/.
"""

import argparse
import csv
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


# =============================================================================
# propose-plan command implementation
# =============================================================================

def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    """Get the set of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def _escape_key_for_path(key: str) -> str:
    """Escape a library_track_key for use in a path segment."""
    # Replace : and / with underscores
    return re.sub(r'[:/]', '_', key)


def _determine_zone(path: str) -> str:
    """Determine the zone classification from a file path."""
    path_lower = path.lower()
    
    # Check for accepted zone patterns
    if '/library/' in path_lower or '/music/library/' in path_lower:
        return 'accepted'
    
    # Check for staging zone patterns
    if '/staging/' in path_lower or '/_staging/' in path_lower:
        return 'staging'
    
    # Check for suspect zone patterns
    if '/suspect/' in path_lower or '/_suspect/' in path_lower:
        return 'suspect'
    
    # Check for quarantine zone patterns
    if '/quarantine/' in path_lower or '/_quarantine/' in path_lower:
        return 'quarantine'
    
    return 'unknown'


def _zone_score(zone: str) -> int:
    """Map zone to base score."""
    scores = {
        'accepted': 40,
        'staging': 30,
        'unknown': 20,
        'suspect': 10,
        'quarantine': 0,
    }
    return scores.get(zone, 20)


def _health_score(health: str | None) -> int:
    """Map metadata_health to score addend."""
    if health is None or health == '':
        return 5
    health_upper = health.upper()
    scores = {
        'OK': 40,
        'WARN': 25,
        'DEGRADED': 10,
        'UNKNOWN': 5,
    }
    return scores.get(health_upper, 5)


def _compute_keeper_scores(
    files: list[dict[str, Any]],
    hub_row: dict[str, Any] | None,
    file_columns: set[str],
) -> list[dict[str, Any]]:
    """Compute keeper_score for each file in a group.
    
    Returns files with added 'keeper_score' and 'zone' fields.
    """
    if not files:
        return files
    
    # Compute completeness bonus (same for all files in group)
    completeness_bonus = 0
    if hub_row:
        # ISRC present
        if hub_row.get('isrc') and str(hub_row.get('isrc', '')).strip():
            completeness_bonus += 5
        # Title and artist present
        title = hub_row.get('title', '') or ''
        artist = hub_row.get('artist', '') or ''
        if title.strip() and artist.strip():
            completeness_bonus += 5
        # Album art presence (check for best_cover_url field)
        if hub_row.get('best_cover_url') and str(hub_row.get('best_cover_url', '')).strip():
            completeness_bonus += 5
    
    # Compute max path length for path bonus
    max_len = max(len(f.get('path', '')) for f in files)
    
    # Check for audio quality columns
    has_bitrate = 'bitrate' in file_columns
    has_bit_depth = 'bit_depth' in file_columns
    has_sample_rate = 'sample_rate' in file_columns
    
    # Compute scores for each file
    for f in files:
        path = f.get('path', '')
        zone = _determine_zone(path)
        f['zone'] = zone
        
        zone_sc = _zone_score(zone)
        health_sc = _health_score(f.get('metadata_health'))
        path_bonus = max(0, min(5, max_len - len(path)))
        
        # Audio quality bonus (up to 10 points)
        audio_bonus = 0
        if has_bitrate or has_bit_depth or has_sample_rate:
            # Simple heuristic: higher values = better
            if has_bitrate and f.get('bitrate'):
                try:
                    br = int(f['bitrate'])
                    if br >= 320000:
                        audio_bonus += 4
                    elif br >= 256000:
                        audio_bonus += 3
                    elif br >= 192000:
                        audio_bonus += 2
                    elif br >= 128000:
                        audio_bonus += 1
                except (ValueError, TypeError):
                    pass
            if has_bit_depth and f.get('bit_depth'):
                try:
                    bd = int(f['bit_depth'])
                    if bd >= 24:
                        audio_bonus += 3
                    elif bd >= 16:
                        audio_bonus += 2
                except (ValueError, TypeError):
                    pass
            if has_sample_rate and f.get('sample_rate'):
                try:
                    sr = int(f['sample_rate'])
                    if sr >= 96000:
                        audio_bonus += 3
                    elif sr >= 48000:
                        audio_bonus += 2
                    elif sr >= 44100:
                        audio_bonus += 1
                except (ValueError, TypeError):
                    pass
        
        f['keeper_score'] = zone_sc + health_sc + completeness_bonus + path_bonus + audio_bonus
    
    return files


def _compute_risk_flags(
    files: list[dict[str, Any]],
    hub_row: dict[str, Any] | None,
    sources: list[dict[str, Any]],
    file_columns: set[str],
) -> dict[str, Any]:
    """Compute risk flags for a group."""
    risk = {
        'duration_spread_ms': 0,
        'health_mix': False,
        'provider_disagreement': False,
        'missing_hub_row': hub_row is None,
    }
    
    # Duration spread
    has_duration = 'canonical_duration' in file_columns
    if has_duration:
        durations_ms = []
        for f in files:
            dur = f.get('canonical_duration')
            if dur is not None:
                try:
                    # canonical_duration is in seconds, convert to ms
                    durations_ms.append(float(dur) * 1000)
                except (ValueError, TypeError):
                    pass
        if len(durations_ms) >= 2:
            risk['duration_spread_ms'] = int(max(durations_ms) - min(durations_ms))
    
    # Health mix
    health_values = set()
    for f in files:
        h = f.get('metadata_health')
        if h:
            health_values.add(h.upper())
    ok_present = 'OK' in health_values
    degraded_warn_present = bool(health_values & {'DEGRADED', 'WARN'})
    if ok_present and degraded_warn_present:
        risk['health_mix'] = True
    
    # Provider disagreement
    if hub_row and hub_row.get('isrc'):
        canonical_isrc = str(hub_row['isrc']).strip().upper()
        for src in sources:
            src_isrc = src.get('isrc')
            if src_isrc:
                src_isrc_upper = str(src_isrc).strip().upper()
                if src_isrc_upper and src_isrc_upper != canonical_isrc:
                    risk['provider_disagreement'] = True
                    break
    
    return risk


def _is_high_risk(risk: dict[str, Any]) -> bool:
    """Check if any risk flags indicate high risk."""
    if risk.get('missing_hub_row'):
        return True
    if risk.get('provider_disagreement'):
        return True
    if risk.get('health_mix'):
        return True
    if risk.get('duration_spread_ms', 0) > 5000:
        return True
    return False


def _get_risk_flag_list(risk: dict[str, Any]) -> list[str]:
    """Get list of active risk flag descriptions."""
    flags = []
    if risk.get('missing_hub_row'):
        flags.append('missing_hub_row')
    if risk.get('provider_disagreement'):
        flags.append('provider_disagreement')
    if risk.get('health_mix'):
        flags.append('health_mix')
    if risk.get('duration_spread_ms', 0) > 5000:
        flags.append(f"duration_spread_ms>{risk['duration_spread_ms']}")
    return flags


def _compute_recommendations(
    files: list[dict[str, Any]],
    keeper_path: str,
    key: str,
    risk: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compute recommendations for each file in a group."""
    recommendations = []
    high_risk = _is_high_risk(risk)
    risk_flags = _get_risk_flag_list(risk) if high_risk else []
    escaped_key = _escape_key_for_path(key)
    
    for f in files:
        path = f['path']
        zone = f.get('zone', 'unknown')
        health = f.get('metadata_health') or 'UNKNOWN'
        health_upper = health.upper() if health else 'UNKNOWN'
        
        rec: dict[str, Any] = {
            'path': path,
        }
        
        if path == keeper_path:
            # This is the keeper
            rec['action'] = 'KEEP'
            rationale = ['highest keeper_score', f'zone={zone}']
            if health_upper == 'OK':
                rationale.append('metadata_health=OK')
            elif health:
                rationale.append(f'metadata_health={health}')
            rec['rationale'] = rationale
        else:
            # Non-keeper: determine action based on zone and health
            if high_risk:
                # High risk group: all non-keepers get REVIEW
                rec['action'] = 'REVIEW'
                rationale = ['high_risk_group'] + risk_flags + [f'zone={zone}', f'metadata_health={health}']
                rec['rationale'] = rationale
            elif health_upper in ('OK', 'WARN') and zone in ('accepted', 'unknown', 'staging'):
                rec['action'] = 'ARCHIVE'
                rec['target'] = f'/archive/{escaped_key}/...'
                rec['rationale'] = ['redundant copy', f'zone={zone}', f'metadata_health={health}']
                rec['safety'] = {'copy_only': True, 'verify_checksum': True}
            elif health_upper == 'DEGRADED' or zone in ('suspect', 'quarantine'):
                rec['action'] = 'QUARANTINE'
                rec['target'] = f'/quarantine/{escaped_key}/...'
                rec['rationale'] = ['lower score than keeper', f'zone={zone}', f'metadata_health={health}']
                rec['safety'] = {'copy_only': True, 'verify_checksum': True}
            else:
                # Insufficient signals
                rec['action'] = 'REVIEW'
                rec['rationale'] = ['insufficient signals', f'zone={zone}', f'metadata_health={health}']
        
        recommendations.append(rec)
    
    return recommendations


def _yaml_escape(value: Any) -> str:
    """Escape a value for YAML output."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Check if we need quoting
    needs_quote = False
    if not s:
        needs_quote = True
    elif s[0] in ('"', "'", '{', '[', '&', '*', '!', '|', '>', '%', '@', '`'):
        needs_quote = True
    elif ':' in s or '#' in s or '\n' in s:
        needs_quote = True
    elif s.lower() in ('true', 'false', 'null', 'yes', 'no', 'on', 'off'):
        needs_quote = True
    
    if needs_quote:
        # Use double quotes and escape internal quotes
        escaped = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    return s


def _write_yaml_plan(
    plan: dict[str, Any],
    output_path: str,
) -> None:
    """Write the plan to a YAML file using simple formatting."""
    lines: list[str] = []
    
    def write_value(val: Any, indent: int = 0) -> None:
        prefix = '  ' * indent
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, (dict, list)) and v:
                    lines.append(f'{prefix}{k}:')
                    write_value(v, indent + 1)
                else:
                    lines.append(f'{prefix}{k}: {_yaml_escape(v)}')
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    # First key on same line as dash
                    first = True
                    for k, v in item.items():
                        if first:
                            if isinstance(v, (dict, list)) and v:
                                lines.append(f'{prefix}- {k}:')
                                write_value(v, indent + 2)
                            else:
                                lines.append(f'{prefix}- {k}: {_yaml_escape(v)}')
                            first = False
                        else:
                            inner_prefix = '  ' * (indent + 1)
                            if isinstance(v, (dict, list)) and v:
                                lines.append(f'{inner_prefix}{k}:')
                                write_value(v, indent + 2)
                            else:
                                lines.append(f'{inner_prefix}{k}: {_yaml_escape(v)}')
                else:
                    lines.append(f'{prefix}- {_yaml_escape(item)}')
        else:
            lines.append(f'{prefix}{_yaml_escape(val)}')
    
    # Write top-level keys in order
    lines.append(f'plan_version: {plan["plan_version"]}')
    lines.append(f'generated_at: {_yaml_escape(plan["generated_at"])}')
    lines.append(f'db: {_yaml_escape(plan["db"])}')
    
    lines.append('scope:')
    for k, v in plan['scope'].items():
        lines.append(f'  {k}: {_yaml_escape(v)}')
    
    lines.append('policy:')
    for k, v in plan['policy'].items():
        lines.append(f'  {k}: {_yaml_escape(v)}')
    
    lines.append('groups:')
    for group in plan['groups']:
        # library_track_key on first line with dash
        lines.append(f'  - library_track_key: {_yaml_escape(group["library_track_key"])}')
        
        # hub
        lines.append('    hub:')
        if group['hub']:
            for k, v in group['hub'].items():
                lines.append(f'      {k}: {_yaml_escape(v)}')
        else:
            lines.append('      null')
        
        # sources
        lines.append('    sources:')
        if group['sources']:
            for src in group['sources']:
                first = True
                for k, v in src.items():
                    if first:
                        lines.append(f'      - {k}: {_yaml_escape(v)}')
                        first = False
                    else:
                        lines.append(f'        {k}: {_yaml_escape(v)}')
        else:
            lines.append('      []')
        
        # risk
        lines.append('    risk:')
        for k, v in group['risk'].items():
            lines.append(f'      {k}: {_yaml_escape(v)}')
        
        # files
        lines.append('    files:')
        for f in group['files']:
            first = True
            for k, v in f.items():
                if first:
                    lines.append(f'      - {k}: {_yaml_escape(v)}')
                    first = False
                else:
                    lines.append(f'        {k}: {_yaml_escape(v)}')
        
        # recommendations
        lines.append('    recommendations:')
        for rec in group['recommendations']:
            first = True
            for k, v in rec.items():
                if k == 'safety' and isinstance(v, dict):
                    lines.append(f'        safety:')
                    for sk, sv in v.items():
                        lines.append(f'          {sk}: {_yaml_escape(sv)}')
                elif k == 'rationale' and isinstance(v, list):
                    lines.append(f'        rationale:')
                    for item in v:
                        lines.append(f'          - {_yaml_escape(item)}')
                elif first:
                    lines.append(f'      - {k}: {_yaml_escape(v)}')
                    first = False
                else:
                    lines.append(f'        {k}: {_yaml_escape(v)}')
    
    # summary
    lines.append('summary:')
    lines.append(f'  groups_total: {plan["summary"]["groups_total"]}')
    lines.append(f'  files_total: {plan["summary"]["files_total"]}')
    lines.append('  actions:')
    for k, v in plan['summary']['actions'].items():
        lines.append(f'    {k}: {v}')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
        f.write('\n')


def _write_csv_plan(
    groups: list[dict[str, Any]],
    output_path: str,
) -> None:
    """Write the plan to a CSV file."""
    fieldnames = [
        'library_track_key',
        'path',
        'role',
        'keeper_score',
        'metadata_health',
        'metadata_health_reason',
        'action',
        'target',
        'zone',
        'duration_spread_ms',
        'risk_flags',
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for group in groups:
            key = group['library_track_key']
            risk = group['risk']
            duration_spread = risk.get('duration_spread_ms', 0)
            risk_flags = ','.join(_get_risk_flag_list(risk))
            
            # Build a map of path -> recommendation
            rec_map = {r['path']: r for r in group['recommendations']}
            
            for f in group['files']:
                path = f['path']
                rec = rec_map.get(path, {})
                
                row = {
                    'library_track_key': key,
                    'path': path,
                    'role': f.get('role', ''),
                    'keeper_score': f.get('keeper_score', ''),
                    'metadata_health': f.get('metadata_health', ''),
                    'metadata_health_reason': f.get('metadata_health_reason', ''),
                    'action': rec.get('action', ''),
                    'target': rec.get('target', ''),
                    'zone': f.get('zone', ''),
                    'duration_spread_ms': duration_spread,
                    'risk_flags': risk_flags,
                }
                writer.writerow(row)


def cmd_propose_plan(args: argparse.Namespace) -> None:
    """Handle the propose-plan command.
    
    Generate a YAML (and optional CSV) dedup plan based on duplicate analysis.
    """
    conn = _connect_db(args.db)
    
    try:
        min_copies = args.min_copies
        limit_groups = args.limit_groups
        output_path = args.out
        csv_path = args.csv
        
        # Get file table columns for optional field detection
        file_columns = _get_table_columns(conn, 'files')
        
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
            (min_copies, limit_groups),
        )
        candidates = cursor.fetchall()
        
        if not candidates:
            print(f"No library_track_key values found with >= {min_copies} files.")
            print("No plan generated.")
            return
        
        print(f"Found {len(candidates)} key(s) with >= {min_copies} files.")
        print(f"Generating plan...")
        
        # Build the plan structure
        groups: list[dict[str, Any]] = []
        action_counts = {'KEEP': 0, 'ARCHIVE': 0, 'QUARANTINE': 0, 'REVIEW': 0}
        total_files = 0
        
        for candidate in candidates:
            key = candidate['library_track_key']
            
            # Fetch hub row
            hub_cursor = conn.execute(
                """
                SELECT *
                FROM library_tracks
                WHERE library_track_key = ?
                """,
                (key,),
            )
            hub_row_raw = hub_cursor.fetchone()
            hub_row = dict(hub_row_raw) if hub_row_raw else None
            
            # Fetch sources
            sources_cursor = conn.execute(
                """
                SELECT *
                FROM library_track_sources
                WHERE library_track_key = ?
                ORDER BY fetched_at DESC
                """,
                (key,),
            )
            sources_raw = sources_cursor.fetchall()
            sources = [dict(row) for row in sources_raw]
            
            # Fetch files
            files_cursor = conn.execute(
                """
                SELECT *
                FROM files
                WHERE library_track_key = ?
                ORDER BY path ASC
                """,
                (key,),
            )
            files_raw = files_cursor.fetchall()
            files = [dict(row) for row in files_raw]
            
            if not files:
                continue
            
            # Compute keeper scores
            files = _compute_keeper_scores(files, hub_row, file_columns)
            
            # Determine keeper (highest score, tie-break by lexicographically smallest path)
            files_sorted = sorted(files, key=lambda f: (-f['keeper_score'], f['path']))
            keeper_path = files_sorted[0]['path']
            
            # Assign roles
            for f in files:
                f['role'] = 'KEEPER' if f['path'] == keeper_path else 'NON_KEEPER'
            
            # Compute risk flags
            risk = _compute_risk_flags(files, hub_row, sources, file_columns)
            
            # Compute recommendations
            recommendations = _compute_recommendations(files, keeper_path, key, risk)
            
            # Count actions
            for rec in recommendations:
                action = rec.get('action', 'REVIEW')
                action_counts[action] = action_counts.get(action, 0) + 1
            
            total_files += len(files)
            
            # Build hub summary for output
            hub_summary = None
            if hub_row:
                hub_summary = {
                    'title': hub_row.get('title'),
                    'artist': hub_row.get('artist'),
                    'album': hub_row.get('album'),
                    'isrc': hub_row.get('isrc'),
                    'duration_ms': hub_row.get('duration_ms'),
                }
                if hub_row.get('updated_at'):
                    hub_summary['updated_at'] = hub_row['updated_at']
            
            # Build sources summary for output
            sources_summary = []
            for src in sources:
                src_entry = {
                    'service': src.get('service'),
                    'service_track_id': src.get('service_track_id'),
                }
                if src.get('match_confidence') is not None:
                    src_entry['match_confidence'] = src['match_confidence']
                if src.get('fetched_at'):
                    src_entry['fetched_at'] = src['fetched_at']
                sources_summary.append(src_entry)
            
            # Build files summary for output
            files_summary = []
            for f in files:
                file_entry = {
                    'path': f['path'],
                    'metadata_health': f.get('metadata_health'),
                    'metadata_health_reason': f.get('metadata_health_reason') or '',
                }
                if f.get('canonical_duration') is not None:
                    file_entry['canonical_duration'] = f['canonical_duration']
                file_entry['keeper_score'] = f['keeper_score']
                file_entry['role'] = f['role']
                files_summary.append(file_entry)
            
            group_entry = {
                'library_track_key': key,
                'hub': hub_summary,
                'sources': sources_summary,
                'risk': risk,
                'files': files_summary,
                'recommendations': recommendations,
            }
            groups.append(group_entry)
        
        # Build the full plan
        plan = {
            'plan_version': 1,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'db': str(Path(args.db).resolve()),
            'scope': {
                'min_copies': min_copies,
                'limit_groups': limit_groups,
            },
            'policy': {
                'keeper_scoring': 'v1',
                'action_rules': 'v1',
            },
            'groups': groups,
            'summary': {
                'groups_total': len(groups),
                'files_total': total_files,
                'actions': action_counts,
            },
        }
        
        # Write YAML output
        _write_yaml_plan(plan, output_path)
        print(f"YAML plan written to: {output_path}")
        
        # Write CSV output if requested
        if csv_path:
            _write_csv_plan(groups, csv_path)
            print(f"CSV plan written to: {csv_path}")
        
        # Print summary
        print()
        print("Summary:")
        print(f"  Groups: {len(groups)}")
        print(f"  Files: {total_files}")
        print(f"  Actions:")
        for action, count in action_counts.items():
            print(f"    {action}: {count}")
    
    finally:
        conn.close()


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="tagslut.cli.track_hub_cli",
        description="Inspect the track hub (library_tracks, library_track_sources) directly.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m tagslut.cli.track_hub_cli track-by-path /Music/Artist/Track.flac --db ./music.db
    python -m tagslut.cli.track_hub_cli track-by-key "isrc:USRC12345678" --db ./music.db
    python -m tagslut.cli.track_hub_cli track-by-key "spotify:4iV5W9uYEdYUVa79Axb7Rh" --db ./music.db
    python -m tagslut.cli.track_hub_cli list-files-for-key "isrc:USRC12345678" --db ./music.db
    python -m tagslut.cli.track_hub_cli find-by-isrc USRC12345678 --db ./music.db
    python -m tagslut.cli.track_hub_cli find-by-provider spotify 4iV5W9uYEdYUVa79Axb7Rh --db ./music.db
    python -m tagslut.cli.track_hub_cli diagnose-duplicates --db ./music.db --min-files 2 --limit 50
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
        description="Derive the library_track_key from an ISRC and display the track hub data.",
    )
    parser_isrc.add_argument(
        "isrc",
        help="The ISRC code (e.g., 'USRC12345678').",
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
        description="Look up library_track_sources by service and service_track_id, then display the linked track hub data.",
    )
    parser_provider.add_argument(
        "service",
        help="The provider service name (e.g., 'spotify', 'beatport').",
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
    parser_diag = subparsers.add_parser(
        "diagnose-duplicates",
        help="Find library_track_key values with multiple files and display diagnostic info.",
        description="Identify potential duplicates by finding keys linked to multiple files.",
    )
    parser_diag.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_diag.add_argument(
        "--min-files",
        type=int,
        default=2,
        help="Minimum number of files per key to include (default: 2).",
    )
    parser_diag.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of keys to display (default: 20).",
    )
    parser_diag.set_defaults(func=cmd_diagnose_duplicates)
    
    # propose-plan subcommand
    parser_plan = subparsers.add_parser(
        "propose-plan",
        help="Generate a YAML (and optional CSV) dedup plan for duplicate files.",
        description="Analyze duplicate files and generate a plan with KEEP/ARCHIVE/QUARANTINE/REVIEW recommendations.",
    )
    parser_plan.add_argument(
        "--db",
        required=True,
        help="Path to the SQLite database file.",
    )
    parser_plan.add_argument(
        "--min-copies",
        type=int,
        default=2,
        help="Minimum number of files per key to include (default: 2).",
    )
    parser_plan.add_argument(
        "--limit-groups",
        type=int,
        default=1000,
        help="Maximum number of groups (keys) to include in the plan (default: 1000).",
    )
    parser_plan.add_argument(
        "--out",
        default="track_hub_plan.yaml",
        help="Output path for YAML plan file (default: track_hub_plan.yaml).",
    )
    parser_plan.add_argument(
        "--csv",
        default=None,
        help="Optional path for CSV export. If omitted, no CSV is written.",
    )
    parser_plan.set_defaults(func=cmd_propose_plan)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
