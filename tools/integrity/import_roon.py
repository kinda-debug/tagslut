#!/usr/bin/env python3
"""
Import Roon library export data for validation and reconciliation.

Roon exports provide:
- High-quality metadata from MusicBrainz and AllMusic (Rovi)
- Duplicate detection (Is Dup? column)
- File paths for matching with our database
- Artist, album, track information
- External IDs (MusicBrainz, Rovi) for cross-referencing

Use cases:
1. Validate our metadata against Roon's curated data
2. Import MusicBrainz IDs for duration validation
3. Cross-check duplicate detection
4. Identify files Roon has but we don't (or vice versa)
"""

import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

import click
import openpyxl

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.storage.schema import get_connection
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils import env_paths

logger = logging.getLogger("dedupe")


@dataclass
class RoonTrack:
    """Represents a track from Roon export."""
    album_artist: str
    album: str
    disc_number: int
    track_number: int
    title: str
    track_artists: str
    composers: str
    external_id: str
    source: str
    is_duplicate: bool
    is_hidden: bool
    tags: str
    path: Path
    
    @property
    def musicbrainz_id(self) -> Optional[str]:
        """Extract MusicBrainz ID from external_id if present."""
        if self.external_id and self.external_id.startswith('mb:'):
            return self.external_id[3:]  # Strip 'mb:' prefix
        return None
    
    @property
    def rovi_id(self) -> Optional[str]:
        """Extract Rovi (AllMusic) ID from external_id if present."""
        if self.external_id and self.external_id.startswith('rovi:'):
            return self.external_id[5:]  # Strip 'rovi:' prefix
        return None


def load_roon_export(xlsx_path: Path) -> list[RoonTrack]:
    """
    Load Roon tracks export from Excel file.
    
    Args:
        xlsx_path: Path to Roon Excel export
        
    Returns:
        List of RoonTrack objects
    """
    logger.info(f"Loading Roon export from {xlsx_path}")
    
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    sheet = wb.active
    
    tracks = []
    
    for row_num in range(2, sheet.max_row + 1):  # Skip header
        row = list(sheet[row_num])
        
        # Extract values (0-indexed from row cells)
        album_artist = row[0].value or ""
        album = row[1].value or ""
        disc_num = row[2].value or 1
        track_num = row[3].value or 0
        title = row[4].value or ""
        track_artists = row[5].value or ""
        composers = row[6].value or ""
        external_id = row[7].value or ""
        source = row[8].value or ""
        is_dup = (row[9].value or "no").lower() == "yes"
        is_hidden = (row[10].value or "no").lower() == "yes"
        tags = row[11].value or ""
        path_str = row[12].value or ""
        
        if not path_str:
            continue
            
        track = RoonTrack(
            album_artist=album_artist,
            album=album,
            disc_number=int(disc_num) if disc_num else 1,
            track_number=int(track_num) if track_num else 0,
            title=title,
            track_artists=track_artists,
            composers=composers,
            external_id=external_id,
            source=source,
            is_duplicate=is_dup,
            is_hidden=is_hidden,
            tags=tags,
            path=Path(path_str),
        )
        
        tracks.append(track)
    
    wb.close()
    logger.info(f"Loaded {len(tracks)} tracks from Roon")
    
    return tracks


def reconcile_with_database(
    roon_tracks: list[RoonTrack],
    db_conn: sqlite3.Connection,
) -> Dict[str, Any]:
    """
    Reconcile Roon data with our database.
    
    Args:
        roon_tracks: List of tracks from Roon
        db_conn: Database connection
        
    Returns:
        Dictionary with reconciliation statistics and findings
    """
    cursor = db_conn.cursor()
    
    stats = {
        "roon_total": len(roon_tracks),
        "matched": 0,
        "missing_in_db": 0,
        "missing_in_roon": 0,
        "musicbrainz_ids_found": 0,
        "rovi_ids_found": 0,
        "roon_duplicates": 0,
        "metadata_updates": 0,
    }
    
    missing_in_db = []
    roon_duplicates = []
    musicbrainz_matches = []
    
    # Index Roon tracks by path
    roon_by_path = {str(t.path): t for t in roon_tracks}
    
    # Check each Roon track against database
    for track in roon_tracks:
        path_str = str(track.path)
        
        # Count external IDs
        if track.musicbrainz_id:
            stats["musicbrainz_ids_found"] += 1
        if track.rovi_id:
            stats["rovi_ids_found"] += 1
        
        # Count Roon-detected duplicates
        if track.is_duplicate:
            stats["roon_duplicates"] += 1
            roon_duplicates.append(track)
        
        # Check if file exists in our database
        cursor.execute("SELECT path, metadata_json FROM files WHERE path = ?", (path_str,))
        row = cursor.fetchone()
        
        if row:
            stats["matched"] += 1
            
            # Check if we can enhance metadata with MusicBrainz ID
            if track.musicbrainz_id:
                metadata = json.loads(row[1]) if row[1] else {}
                if 'musicbrainz_trackid' not in metadata:
                    musicbrainz_matches.append({
                        'path': path_str,
                        'musicbrainz_id': track.musicbrainz_id,
                        'title': track.title,
                        'album': track.album,
                    })
        else:
            stats["missing_in_db"] += 1
            missing_in_db.append(track)
    
    # Find files in DB but not in Roon
    cursor.execute("SELECT COUNT(*) FROM files")
    db_total = cursor.fetchone()[0]
    stats["missing_in_roon"] = db_total - stats["matched"]
    
    logger.info("=" * 80)
    logger.info("ROON RECONCILIATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Roon tracks: {stats['roon_total']}")
    logger.info(f"Database files: {db_total}")
    logger.info(f"Matched: {stats['matched']}")
    logger.info(f"In Roon but not DB: {stats['missing_in_db']}")
    logger.info(f"In DB but not Roon: {stats['missing_in_roon']}")
    logger.info(f"")
    logger.info(f"MusicBrainz IDs available: {stats['musicbrainz_ids_found']}")
    logger.info(f"Rovi (AllMusic) IDs available: {stats['rovi_ids_found']}")
    logger.info(f"Roon-detected duplicates: {stats['roon_duplicates']}")
    logger.info(f"Can enhance with MusicBrainz: {len(musicbrainz_matches)}")
    
    return {
        "stats": stats,
        "missing_in_db": missing_in_db,
        "roon_duplicates": roon_duplicates,
        "musicbrainz_matches": musicbrainz_matches,
    }


def update_database_from_roon(
    roon_tracks: list[RoonTrack],
    db_conn: sqlite3.Connection,
    dry_run: bool = True,
) -> int:
    """
    Update database with MusicBrainz IDs from Roon.
    
    Args:
        roon_tracks: List of tracks from Roon
        db_conn: Database connection
        dry_run: If True, don't commit changes
        
    Returns:
        Number of records updated
    """
    cursor = db_conn.cursor()
    updated = 0
    
    for track in roon_tracks:
        if not track.musicbrainz_id:
            continue
            
        path_str = str(track.path)
        
        # Get current metadata
        cursor.execute("SELECT metadata_json FROM files WHERE path = ?", (path_str,))
        row = cursor.fetchone()
        
        if not row:
            continue
        
        metadata = json.loads(row[0]) if row[0] else {}
        
        # Check if we need to add MusicBrainz ID
        if 'musicbrainz_trackid' not in metadata:
            metadata['musicbrainz_trackid'] = track.musicbrainz_id
            
            if not dry_run:
                cursor.execute(
                    "UPDATE files SET metadata_json = ? WHERE path = ?",
                    (json.dumps(metadata), path_str)
                )
            
            updated += 1
            logger.debug(f"Updated {path_str} with MusicBrainz ID {track.musicbrainz_id}")
    
    if not dry_run:
        db_conn.commit()
        logger.info(f"✓ Updated {updated} records with MusicBrainz IDs")
    else:
        logger.info(f"Dry-run: Would update {updated} records with MusicBrainz IDs")
    
    return updated


@click.command()
@click.option(
    "--roon-export",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to Roon Excel export (.xlsx)",
)
@click.option(
    "--db",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to SQLite database (default: from config/environment)",
)
@click.option(
    "--update-musicbrainz",
    is_flag=True,
    help="Update database with MusicBrainz IDs from Roon",
)
@click.option(
    "--execute",
    is_flag=True,
    help="Actually perform updates (default is dry-run)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Write reconciliation report to JSON file",
)
@common_options
def main(
    roon_export: str,
    db: str,
    update_musicbrainz: bool,
    execute: bool,
    output: Optional[str],
    verbose: bool,
    config: Optional[str],
):
    """
    Import and reconcile Roon library export data.
    
    Roon provides high-quality metadata from MusicBrainz and AllMusic.
    This tool helps you:
    
    1. Reconcile Roon's library with your database
    2. Import MusicBrainz IDs for duration validation
    3. Cross-check duplicate detection
    4. Identify missing files
    
    Examples:
    
        # View reconciliation report
        python tools/integrity/import_roon.py --roon-export roon.xlsx --db music.db
        
        # Update database with MusicBrainz IDs (dry-run)
        python tools/integrity/import_roon.py --roon-export roon.xlsx --db music.db --update-musicbrainz
        
        # Actually perform updates
        python tools/integrity/import_roon.py --roon-export roon.xlsx --db music.db --update-musicbrainz --execute
        
        # Generate JSON report
        python tools/integrity/import_roon.py --roon-export roon.xlsx --db music.db -o roon_report.json
    """
    configure_execution(verbose, config)
    
    # Get database path from config if not provided
    if not db:
        db = env_paths.get_db_path()
        if not db:
            logger.error("No database path found in config. Set DEDUPE_DB environment variable or use --db")
            raise click.ClickException("Database path not configured")
        logger.info(f"Using database from config: {db}")
    
    # Load Roon export
    roon_tracks = load_roon_export(Path(roon_export))
    
    # Connect to database
    db_conn = get_connection(Path(db))
    
    # Reconcile
    results = reconcile_with_database(roon_tracks, db_conn)
    
    # Update MusicBrainz IDs if requested
    if update_musicbrainz:
        dry_run = not execute
        updated = update_database_from_roon(roon_tracks, db_conn, dry_run=dry_run)
        results["musicbrainz_updates"] = updated
    
    # Write JSON report
    if output:
        report = {
            "summary": results["stats"],
            "missing_in_db": [
                {
                    "path": str(t.path),
                    "title": t.title,
                    "album": t.album,
                    "album_artist": t.album_artist,
                    "musicbrainz_id": t.musicbrainz_id,
                }
                for t in results["missing_in_db"][:100]  # Limit to first 100
            ],
            "roon_duplicates": [
                {
                    "path": str(t.path),
                    "title": t.title,
                    "album": t.album,
                    "musicbrainz_id": t.musicbrainz_id,
                }
                for t in results["roon_duplicates"][:100]
            ],
            "can_add_musicbrainz": [
                m for m in results["musicbrainz_matches"][:100]
            ],
        }
        
        with open(output, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"\n✓ JSON report written to: {output}")
    
    db_conn.close()


if __name__ == "__main__":
    main()
