#!/usr/bin/env python3
"""Migrate metadata schema from individual columns to JSON storage.

Old schema: artist, album, title, date, genre, etc. (14 columns)
New schema: vorbis_tags (JSON), audio_properties (JSON), format_info (JSON)
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path.home() / ".cache" / "file_dupes.db"


def migrate_schema():
    """Migrate from individual columns to JSON storage."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("Step 1: Check current schema...")
    cur.execute("PRAGMA table_info(file_hashes)")
    cols = {row[1] for row in cur.fetchall()}
    print(f"  Columns: {len(cols)}")
    
    # Add new JSON columns if they don't exist
    print("\nStep 2: Add JSON columns...")
    new_cols = [
        ("vorbis_tags", "TEXT"),
        ("audio_properties", "TEXT"),
        ("format_info", "TEXT"),
        ("artwork_count", "INTEGER"),
    ]
    
    for col_name, col_type in new_cols:
        if col_name not in cols:
            print(f"  Adding {col_name}")
            cur.execute(
                f"ALTER TABLE file_hashes ADD COLUMN {col_name} {col_type}"
            )
            cols.add(col_name)
    
    # Migrate existing metadata to JSON
    print("\nStep 3: Migrate existing metadata to JSON...")
    
    # Old individual columns that store Vorbis tag data
    old_tag_cols = [
        'artist', 'album', 'title', 'date', 'genre',
        'tracknumber', 'albumartist'
    ]
    
    # Audio property columns
    old_audio_cols = [
        'bitrate', 'sample_rate', 'channels', 'duration_sec'
    ]
    
    # Check if we have data to migrate
    cur.execute("SELECT COUNT(*) FROM file_hashes WHERE metadata_scanned = 1")
    scanned_count = cur.fetchone()[0]
    print(f"  Found {scanned_count} files with old metadata")
    
    if scanned_count > 0:
        # Build SELECT for old columns
        select_cols = ['file_path'] + old_tag_cols + old_audio_cols + [
            'has_artwork', 'encoder'
        ]
        existing_old_cols = [c for c in select_cols if c in cols]
        
        cur.execute(f"""
            SELECT {', '.join(existing_old_cols)}
            FROM file_hashes
            WHERE metadata_scanned = 1
        """)
        
        migrated = 0
        for row in cur.fetchall():
            file_path = row[0]
            values = dict(zip(existing_old_cols[1:], row[1:]))
            
            # Build vorbis_tags JSON
            vorbis_tags = {}
            for tag in old_tag_cols:
                if tag in values and values[tag]:
                    # Map to uppercase Vorbis tag names
                    tag_name = tag.upper()
                    vorbis_tags[tag_name] = values[tag]
            
            # Build audio_properties JSON
            audio_props = {}
            for prop in old_audio_cols:
                if prop in values and values[prop] is not None:
                    audio_props[prop] = values[prop]
            
            if 'encoder' in values and values['encoder']:
                audio_props['encoder'] = values['encoder']
            
            # Update with JSON data
            cur.execute("""
                UPDATE file_hashes SET
                    vorbis_tags = ?,
                    audio_properties = ?,
                    artwork_count = ?
                WHERE file_path = ?
            """, (
                json.dumps(vorbis_tags) if vorbis_tags else None,
                json.dumps(audio_props) if audio_props else None,
                1 if values.get('has_artwork') else 0,
                file_path
            ))
            
            migrated += 1
            if migrated % 50 == 0:
                print(f"    Migrated {migrated}/{scanned_count}...")
        
        print(f"  Migrated {migrated} files")
        conn.commit()
    
    # Don't drop old columns yet - keep them for reference
    # User can manually drop them later if desired
    print("\nStep 4: Old columns retained for reference")
    print("  To drop manually later: ALTER TABLE file_hashes DROP COLUMN artist;")
    
    conn.close()
    print("\nMigration complete!")


if __name__ == '__main__':
    migrate_schema()
