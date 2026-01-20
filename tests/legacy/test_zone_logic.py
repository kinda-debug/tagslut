#!/usr/bin/env python3
"""Test the new auto-zone assignment logic."""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dedupe_v2.core.zone_assignment import determine_zone

def test_zone_logic():
    """Test various scenarios for zone assignment."""
    
    library = Path("/Volumes/COMMUNE/M/Library")
    staging = Path("/Volumes/COMMUNE/M/_staging")
    
    test_cases = [
        # (integrity_ok, is_duplicate, path, expected_zone, description)
        (False, False, Path("/Volumes/Vault/file.flac"), "suspect", "Integrity failed"),
        (True, True, Path("/Volumes/COMMUNE/M/Library/file.flac"), "suspect", "Duplicate in library"),
        (True, False, Path("/Volumes/COMMUNE/M/Library/artist/album/01.flac"), "accepted", "Clean file in library"),
        (True, False, Path("/Volumes/COMMUNE/M/_staging/new/01.flac"), "staging", "Clean file in staging"),
        (True, False, Path("/Volumes/Vault/Vault/unknown/01.flac"), "suspect", "Clean file in unknown location"),
        (True, True, Path("/Volumes/Vault/Vault/dup.flac"), "suspect", "Duplicate in vault"),
    ]
    
    print("=" * 80)
    print("ZONE ASSIGNMENT LOGIC TEST")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for integrity, is_dup, path, expected, desc in test_cases:
        result = determine_zone(
            integrity_ok=integrity,
            is_duplicate=is_dup,
            file_path=path,
            library_root=library,
            staging_root=staging,
        )
        
        status = "✓" if result == expected else "✗"
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {desc}")
        print(f"  Integrity: {integrity}, Duplicate: {is_dup}")
        print(f"  Path: {path}")
        print(f"  Expected: {expected}, Got: {result}")
        print()
    
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = test_zone_logic()
    sys.exit(0 if success else 1)
