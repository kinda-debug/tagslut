#!/usr/bin/env python3
"""
Quarantine small/short duplicate files for later AcoustID verification.
Moves files < 10 MB and < 90 seconds to quarantine zones.
"""

import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = 'artifacts/db/music.db'
SIZE_THRESHOLD_MB = 10
DURATION_THRESHOLD_SEC = 90

# Quarantine directories by volume
QUARANTINE_DIRS = {
    '/Volumes/RECOVERY_TARGET': '/Volumes/RECOVERY_TARGET/_QUARANTINE',
    '/Volumes/COMMUNE': '/Volumes/COMMUNE/_QUARANTINE'
}

def get_file_size_mb(path):
    """Get file size in MB."""
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except:
        return 0

def get_volume_root(path):
    """Extract volume root from path."""
    parts = path.split('/')
    if len(parts) >= 3:
        return '/' + parts[1] + '/' + parts[2]
    return None

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Find duplicate files that are small and short
    query = """
    WITH ranked AS (
        SELECT path, checksum, library, zone, duration, 
               ROW_NUMBER() OVER (PARTITION BY checksum ORDER BY 
                   CASE zone WHEN 'accepted' THEN 1 WHEN 'staging' THEN 2 
                             WHEN 'suspect' THEN 3 ELSE 4 END) as rank,
               COUNT(*) OVER (PARTITION BY checksum) as total_copies
        FROM files 
        WHERE checksum NOT LIKE 'NOT_SCANNED%'
    )
    SELECT path, checksum, library, zone, duration, rank, total_copies
    FROM ranked
    WHERE total_copies > 1 
      AND duration < ?
      AND rank > 1
      AND zone != 'quarantine'
    ORDER BY checksum, rank
    """
    
    cursor.execute(query, (DURATION_THRESHOLD_SEC,))
    candidates = cursor.fetchall()
    
    print(f"Found {len(candidates)} duplicate files < {DURATION_THRESHOLD_SEC}s duration")
    print("Checking file sizes...")
    
    to_quarantine = []
    for path, checksum, library, zone, duration, rank, total_copies in candidates:
        if not os.path.exists(path):
            print(f"  ⚠ Missing: {path}")
            continue
            
        size_mb = get_file_size_mb(path)
        if size_mb < SIZE_THRESHOLD_MB:
            to_quarantine.append((path, checksum, library, zone, duration, size_mb, total_copies))
    
    print(f"\n{len(to_quarantine)} files meet criteria (< {SIZE_THRESHOLD_MB} MB and < {DURATION_THRESHOLD_SEC}s)")
    
    if not to_quarantine:
        print("Nothing to quarantine.")
        conn.close()
        return
    
    # Show summary
    print("\nQuarantine Summary:")
    for vol, qdir in QUARANTINE_DIRS.items():
        count = sum(1 for p, *_ in to_quarantine if p.startswith(vol))
        if count > 0:
            print(f"  {vol}: {count} files → {qdir}")
    
    # Ask for confirmation
    response = input(f"\nQuarantine {len(to_quarantine)} files? [y/N]: ")
    if response.lower() != 'y':
        print("Cancelled.")
        conn.close()
        return
    
    # Create quarantine directories
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    for qdir in QUARANTINE_DIRS.values():
        qdir_timestamped = f"{qdir}/small_dupes_{timestamp}"
        os.makedirs(qdir_timestamped, exist_ok=True)
    
    # Move files and update database
    moved_count = 0
    for path, checksum, library, zone, duration, size_mb, total_copies in to_quarantine:
        volume_root = get_volume_root(path)
        if volume_root not in QUARANTINE_DIRS:
            print(f"  ⚠ Unknown volume: {path}")
            continue
        
        qdir = QUARANTINE_DIRS[volume_root]
        qdir_timestamped = f"{qdir}/small_dupes_{timestamp}"
        
        # Preserve relative structure
        rel_path = os.path.relpath(path, volume_root)
        dest_path = os.path.join(qdir_timestamped, rel_path)
        dest_dir = os.path.dirname(dest_path)
        
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(path, dest_path)
            
            # Update database
            cursor.execute("""
                UPDATE files 
                SET path = ?, zone = 'quarantine' 
                WHERE path = ?
            """, (dest_path, path))
            
            moved_count += 1
            if moved_count % 10 == 0:
                print(f"  Moved {moved_count}/{len(to_quarantine)}...")
        
        except Exception as e:
            print(f"  ✗ Error moving {path}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✓ Quarantined {moved_count} files")
    print(f"  Updated database zone to 'quarantine'")
    print(f"\nNext: Use AcoustID fingerprinting to decide which to keep")

if __name__ == '__main__':
    main()
