#!/usr/bin/env python3
"""Test database compatibility with v2 zone logic."""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import existing database utilities
from dedupe.utils import env_paths
from dedupe.utils.db import open_db

# Import new zone logic
from dedupe_v2.core.zone_assignment import determine_zone


def test_database_compatibility():
    """Verify we can read existing database and apply new zone logic."""
    
    print("=" * 80)
    print("DATABASE COMPATIBILITY TEST")
    print("=" * 80)
    
    # Get database path from environment
    db_path = env_paths.get_db_path()
    if not db_path:
        print("✗ No database configured in .env")
        return False
    
    print(f"Database: {db_path}")
    
    if not db_path.exists():
        print(f"✗ Database does not exist: {db_path}")
        return False
    
    print("✓ Database found")
    
    # Open database (read-only test)
    try:
        from dedupe.utils.db import resolve_db_path
        resolution = resolve_db_path(
            cli_db=db_path,
            allow_create=False,
            purpose="read",
        )
        conn = open_db(resolution)
        print("✓ Database opened successfully")
    except Exception as e:
        print(f"✗ Failed to open database: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Read sample files
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                path, 
                flac_ok, 
                zone,
                sha256
            FROM files 
            WHERE flac_ok IS NOT NULL
            LIMIT 10
        """)
        
        rows = cursor.fetchall()
        print(f"✓ Read {len(rows)} sample files from database")
        
        if not rows:
            print("  (No scanned files found - database may be empty)")
            conn.close()
            return True
        
    except Exception as e:
        print(f"✗ Failed to query database: {e}")
        conn.close()
        return False
    
    # Test zone reassignment logic
    print("\n" + "=" * 80)
    print("ZONE REASSIGNMENT TEST (Sample Files)")
    print("=" * 80)
    
    library_root = env_paths.get_volume("library")
    staging_root = env_paths.get_volume("staging")
    
    # Count duplicates for each file
    cursor.execute("""
        SELECT sha256, COUNT(*) as count
        FROM files
        WHERE sha256 IS NOT NULL
        GROUP BY sha256
        HAVING count > 1
    """)
    duplicate_hashes = {row[0] for row in cursor.fetchall()}
    print(f"Found {len(duplicate_hashes)} duplicate hash groups in database")
    
    changes = 0
    same = 0
    
    for path_str, flac_ok, old_zone, sha256 in rows:
        file_path = Path(path_str)
        is_duplicate = sha256 in duplicate_hashes
        
        new_zone = determine_zone(
            integrity_ok=bool(flac_ok),
            is_duplicate=is_duplicate,
            file_path=file_path,
            library_root=library_root,
            staging_root=staging_root,
        )
        
        if new_zone != old_zone:
            changes += 1
            print(f"  {old_zone} → {new_zone}: {file_path.name}")
        else:
            same += 1
    
    print()
    print(f"✓ Zone compatibility test complete")
    print(f"  Same: {same}, Changed: {changes}")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("COMPATIBILITY TEST PASSED")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Review zone changes above")
    print("2. If acceptable, integrate zone_assignment.py into scanner")
    print("3. Remove --zone flag from scan.py")
    print("4. Update integrity_scanner.py to call determine_zone()")
    
    return True


if __name__ == "__main__":
    success = test_database_compatibility()
    sys.exit(0 if success else 1)
