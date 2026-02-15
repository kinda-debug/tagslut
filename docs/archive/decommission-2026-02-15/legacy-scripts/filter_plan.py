#!/usr/bin/env python3
"""
Filter removal plan to only include files NOT in the destination library.
This ensures we never accidentally quarantine files from /Volumes/SAD/MUSIC.
"""

import csv
import sys
from pathlib import Path

def filter_plan(input_csv: str, output_csv: str, destination_prefix: str):
    """
    Filter plan to exclude any rows where the file to quarantine is in the destination.
    
    Args:
        input_csv: Original plan.csv
        output_csv: Filtered output
        destination_prefix: Path prefix to protect (e.g., /Volumes/SAD/MUSIC)
    """
    
    kept_rows = []
    protected_count = 0
    
    with open(input_csv, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            path = row['path']
            
            # Skip if this file is in the protected destination
            if path.startswith(destination_prefix):
                protected_count += 1
                continue
            
            kept_rows.append(row)
    
    # Write filtered plan
    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_rows)
    
    print(f"Original plan: {len(kept_rows) + protected_count} files to quarantine")
    print(f"Protected (in {destination_prefix}): {protected_count} files")
    print(f"Filtered plan: {len(kept_rows)} files to quarantine")
    print(f"\nFiltered plan written to: {output_csv}")
    
    # Summary by source zone
    zone_counts = {}
    for row in kept_rows:
        zone = row['source_zone']
        zone_counts[zone] = zone_counts.get(zone, 0) + 1
    
    print("\nFiles to quarantine by current location:")
    for zone, count in sorted(zone_counts.items()):
        print(f"  {zone}: {count}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python filter_plan.py plan.csv [output.csv] [destination_prefix]")
        sys.exit(1)
    
    input_csv = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) > 2 else "plan_filtered.csv"
    destination_prefix = sys.argv[3] if len(sys.argv) > 3 else "/Volumes/SAD/MUSIC"
    
    filter_plan(input_csv, output_csv, destination_prefix)
