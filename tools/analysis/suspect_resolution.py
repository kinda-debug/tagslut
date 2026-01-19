from __future__ import annotations
import os
import sqlite3
import pandas as pd
from pathlib import Path
from dedupe.utils.env_paths import get_db_path

def analyze_suspect_files():
    db_path = get_db_path()
    suspect_list_file = Path("suspect_files_full_list.txt")

    if not suspect_list_file.exists():
        print(f"Error: {suspect_list_file} not found")
        return

    with open(suspect_list_file, "r") as f:
        suspect_paths = [line.strip() for line in f if line.strip()]

    print(f"Analyzing {len(suspect_paths)} files...")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    results = []

    for path in suspect_paths:
        p = Path(path)
        filename = p.name

        # 1. Check for junk
        if filename.startswith("._") or filename == ".DS_Store":
            results.append({
                "path": path,
                "status": "JUNK",
                "reason": "macOS metadata file",
                "action": "DELETE",
                "canonical_match": ""
            })
            continue

        # 2. Query DB for this file
        cursor = conn.execute("SELECT * FROM files WHERE path = ?", (path,))
        file_row = cursor.fetchone()

        if not file_row:
            results.append({
                "path": path,
                "status": "UNTRACKED",
                "reason": "Not indexed in database",
                "action": "SCAN",
                "canonical_match": ""
            })
            continue

        sha256 = file_row["sha256"]
        if not sha256:
            results.append({
                "path": path,
                "status": "NO_HASH",
                "reason": "File indexed but hash missing",
                "action": "SCAN_HASH",
                "canonical_match": ""
            })
            continue

        # 3. Look for duplicates in accepted zone
        cursor = conn.execute(
            "SELECT path FROM files WHERE sha256 = ? AND zone = 'accepted' AND path != ?",
            (sha256, path)
        )
        match = cursor.fetchone()

        if match:
            results.append({
                "path": path,
                "status": "DUPLICATE",
                "reason": f"Exact match found in Library",
                "action": "QUARANTINE",
                "canonical_match": match["path"]
            })
        else:
            # 4. Check if it exists in other zones (e.g. staging)
            cursor = conn.execute(
                "SELECT path, zone FROM files WHERE sha256 = ? AND path != ?",
                (sha256, path)
            )
            other_match = cursor.fetchone()
            if other_match:
                results.append({
                    "path": path,
                    "status": "REDUNDANT",
                    "reason": f"Match found in {other_match['zone']} zone",
                    "action": "QUARANTINE",
                    "canonical_match": other_match["path"]
                })
            else:
                results.append({
                    "path": path,
                    "status": "UNIQUE",
                    "reason": "No duplicates found",
                    "action": "PROMOTE",
                    "canonical_match": ""
                })

    conn.close()

    df = pd.DataFrame(results)
    report_path = "suspect_resolution_report.csv"
    df.to_csv(report_path, index=False)

    print(f"Report generated: {report_path}")
    print("\nSummary:")
    print(df["action"].value_counts())

if __name__ == "__main__":
    analyze_suspect_files()
