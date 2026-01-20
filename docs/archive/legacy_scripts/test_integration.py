#!/usr/bin/env python3
"""Quick integration test for auto-zone assignment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dedupe.utils import env_paths

print("=" * 80)
print("AUTO-ZONE INTEGRATION TEST")
print("=" * 80)

# Test 1: Check env_paths are loaded
print("\n1. Testing environment configuration...")
db_path = env_paths.get_db_path()
library_root = env_paths.get_volume("library")
staging_root = env_paths.get_volume("staging")

print(f"   Database:     {db_path}")
print(f"   Library Root: {library_root}")
print(f"   Staging Root: {staging_root}")

if not db_path:
    print("   ✗ Database path not configured!")
    sys.exit(1)

print("   ✓ Environment configured")

# Test 2: Check zone_assignment module imports
print("\n2. Testing zone_assignment module...")
try:
    from dedupe.core.zone_assignment import determine_zone
    print("   ✓ Module imported successfully")
except ImportError as e:
    print(f"   ✗ Import failed: {e}")
    sys.exit(1)

# Test 3: Check metadata module updated
print("\n3. Testing metadata module integration...")
try:
    from dedupe.core.metadata import extract_metadata
    import inspect
    sig = inspect.signature(extract_metadata)
    params = list(sig.parameters.keys())
    
    if 'library_root' in params and 'staging_root' in params:
        print("   ✓ Metadata module accepts library_root and staging_root")
    else:
        print(f"   ✗ Missing parameters. Found: {params}")
        sys.exit(1)
        
    if 'zone' in params:
        print("   ✗ Old 'zone' parameter still present!")
        sys.exit(1)
    else:
        print("   ✓ Old 'zone' parameter removed")
        
except Exception as e:
    print(f"   ✗ Test failed: {e}")
    sys.exit(1)

# Test 4: Check scanner updated
print("\n4. Testing scanner module integration...")
try:
    from dedupe.integrity_scanner import scan_library
    sig = inspect.signature(scan_library)
    params = list(sig.parameters.keys())
    
    if 'zone' in params:
        print(f"   ✗ Old 'zone' parameter still present in scan_library!")
        sys.exit(1)
    else:
        print("   ✓ Old 'zone' parameter removed from scan_library")
        
except Exception as e:
    print(f"   ✗ Test failed: {e}")
    sys.exit(1)

# Test 5: Quick zone determination test
print("\n5. Testing zone determination logic...")
test_path = Path("/Volumes/COMMUNE/M/Library/Artist/Album/01.flac")
zone = determine_zone(
    integrity_ok=True,
    is_duplicate=False,
    file_path=test_path,
    library_root=Path("/Volumes/COMMUNE/M/Library"),
    staging_root=Path("/Volumes/COMMUNE/M/_staging"),
)

if zone == "accepted":
    print(f"   ✓ Clean library file correctly assigned to 'accepted'")
else:
    print(f"   ✗ Expected 'accepted', got '{zone}'")
    sys.exit(1)

print("\n" + "=" * 80)
print("✓ ALL INTEGRATION TESTS PASSED")
print("=" * 80)
print("\nNext steps:")
print("1. Test with actual scan: ./tools/integrity/scan.py <path> --db <db>")
print("2. Zones will be auto-assigned based on:")
print("   - Integrity check results (flac -t)")
print("   - Duplicate detection (SHA256)")
print("   - File location (library vs staging vs other)")
print("3. No --zone flag needed anymore")
