from __future__ import annotations
import sqlite3
import csv
import os
from pathlib import Path
from collections import defaultdict

def get_db_path():
    return os.environ.get("DEDUPE_DB", "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db")

def main():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"Reading duplicates from {db_path}...")

    # Get all files with a SHA256 checksum, grouped by checksum
    # Only consider groups with more than 1 file
    query = """
    SELECT sha256, count(*) as group_count
    FROM files
    WHERE sha256 IS NOT NULL AND sha256 != ''
    GROUP BY sha256
    HAVING group_count > 1
    """
    cursor.execute(query)
    duplicate_groups = cursor.fetchall()

    print(f"Found {len(duplicate_groups)} duplicate SHA256 groups.")

    removal_plan = []
    total_files_to_remove = 0

    for group in duplicate_groups:
        sha256 = group['sha256']

        cursor.execute("SELECT path, zone, size, bitrate, sample_rate FROM files WHERE sha256 = ?", (sha256,))
        files = [dict(row) for row in cursor.fetchall()]

        # Sort files to pick a consistent keeper.
        # 1. Prefer Library_CANONICAL
        # 2. Prefer Untitled/Recovered_FLACs
        # 3. Prefer shorter paths
        # 4. Alphabetical

        def sort_key(f):
            path = f['path']
            # Lower score is better
            score = 10
            if "Library_CANONICAL" in path:
                score = 1
            elif "Untitled/Recovered_FLACs" in path:
                score = 2

            return (score, len(path), path)

        files.sort(key=sort_key)

        keeper = files[0]

        # Filter files to remove based on exclusions
        exclude_prefixes = [
            "/Volumes/bad/archive/music",
            "/Volumes/xtralegroom",
            "/Volumes/COMMUNE/INCOMING"
        ]

        to_remove = []
        for f in files[1:]:
            path = f['path']
            is_excluded = False
            for prefix in exclude_prefixes:
                if path.startswith(prefix):
                    is_excluded = True
                    break
            if not is_excluded:
                to_remove.append(f)

        for f in to_remove:
            removal_plan.append({
                "path": f['path'],
                "sha256": sha256,
                "reason": "SHA256 duplicate",
                "keeper_path": keeper['path']
            })
            total_files_to_remove += 1

    # Write the plan
    output_file = "equal_treatment_dedupe_plan.csv"
    with open(output_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "sha256", "reason", "keeper_path"])
        writer.writeheader()
        writer.writerows(removal_plan)

    print(f"Wrote {total_files_to_remove} files to move to {output_file}")

    # Print summary
    print("\n--- Summary ---")
    print(f"Total unique files (SHA256 groups): {len(duplicate_groups)}")
    print(f"Total redundant files to quarantine: {total_files_to_remove}")

    # Breakdown by Volume
    volume_counts = defaultdict(int)
    for row in removal_plan:
        path = row['path']
        if path.startswith("/Volumes/"):
            vol = path.split("/")[2]
            volume_counts[vol] += 1
        else:
            volume_counts["Other"] += 1

    print("\nFiles to be removed per volume:")
    for vol, count in volume_counts.items():
        print(f"  {vol}: {count}")

if __name__ == "__main__":
    main()
