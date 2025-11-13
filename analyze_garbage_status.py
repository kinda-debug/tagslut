#!/usr/bin/env python3
"""
Analyze what happened with Garbage folder deletion.
"""
import csv
from pathlib import Path

# Read move plan
move_plan = Path('/Users/georgeskhawam/dedupe_repo/artifacts/reports/library_move_plan.csv')
with open(move_plan) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Count files by source in move plan
garbage_in_plan = [r for r in rows if r['source_root'] == 'Garbage']
quarantine_in_plan = [r for r in rows if r['source_root'] == 'Quarantine']
music_in_plan = [r for r in rows if r['source_root'] == 'MUSIC']

print("=" * 80)
print("MOVE PLAN ANALYSIS")
print("=" * 80)
print(f"\nTotal files in move plan: {len(rows)}")
print(f"  From MUSIC:     {len(music_in_plan)} files")
print(f"  From Quarantine: {len(quarantine_in_plan)} files")
print(f"  From Garbage:   {len(garbage_in_plan)} files")

print("\n" + "=" * 80)
print("WHAT SHOULD EXIST:")
print("=" * 80)

print("\nFiles that SHOULD BE in /Volumes/dotad/NEW_LIBRARY/Garbage:")
print(f"  {len(garbage_in_plan)} FLAC files from original Garbage folder")

print("\nFiles that SHOULD HAVE BEEN DELETED from /Volumes/dotad/Garbage:")
print("  All OTHER files that were NOT in the move plan")
print("  (These were duplicate copies kept in MUSIC or Quarantine instead)")

print("\n" + "=" * 80)
print("CRITICAL:")
print("=" * 80)
print("\nThe Garbage folder should ONLY contain:")
print("  - 2,929 unique audio files (those selected for NEW_LIBRARY)")
print("\nEverything else in original Garbage was a DUPLICATE")
print("  and should have been deleted.")

print("\nIf original /Volumes/dotad/Garbage still has thousands of files,")
print("  the deletion was INCOMPLETE or STOPPED.")
