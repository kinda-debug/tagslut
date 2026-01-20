
import sqlite3
import csv
from pathlib import Path

db_path = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_20260119/music.db"
manifest_path = "RECOVERY_MANIFEST.csv"
output_path = "restoration_readiness_report.csv"

def generate_report():
    if not Path(manifest_path).exists():
        print(f"Error: {manifest_path} not found")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all hashes from the Recovered_FLACs scan (Session 33 or any file in that path)
    # We'll just look for any file currently on disk that matches a missing hash
    print("Fetching available hashes from database...")
    cursor = conn.execute("SELECT sha256, path FROM files WHERE sha256 IS NOT NULL")
    available_map = {}
    for row in cursor:
        p = Path(row['path'])
        if p.exists(): # Only count if it actually exists on disk somewhere
            available_map[row['sha256']] = row['path']

    print(f"Reading {manifest_path}...")
    with open(manifest_path, "r") as f:
        reader = csv.DictReader(f)
        missing_items = list(reader)

    results = []
    found_count = 0

    for item in missing_items:
        sha = item['SHA256']
        target = item['TARGET_PATH']

        status = "MISSING"
        current_loc = ""

        if sha in available_map:
            status = "FOUND"
            current_loc = available_map[sha]
            found_count += 1

        results.append({
            "TARGET_PATH": target,
            "SHA256": sha,
            "STATUS": status,
            "CURRENT_LOCATION": current_loc
        })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["TARGET_PATH", "SHA256", "STATUS", "CURRENT_LOCATION"])
        writer.writeheader()
        writer.writerows(results)

    print(f"Report generated: {output_path}")
    print(f"Summary: Found {found_count} out of {len(missing_items)} missing files.")
    conn.close()

if __name__ == "__main__":
    generate_report()
