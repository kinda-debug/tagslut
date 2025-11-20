#!/usr/bin/env python3
import csv
import os
import shutil
import sys

CSV_PATH = "artifacts/reports/gemini_safe_to_delete.csv"
QUAR = "/Volumes/dotad/QUARANTINE_GEMINI"

def main():
    if not os.path.exists(CSV_PATH):
        print(f"CSV not found: {CSV_PATH}")
        sys.exit(1)

    os.makedirs(QUAR, exist_ok=True)

    moved = 0
    skipped = 0
    missing = 0

    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        candidates = ["delete_path", "gemini_path", "music_match_path", "path", "file", "filepath", "src", "source", "source_path"]
        col = None
        for candidate in candidates:
            for field in reader.fieldnames:
                if field.lower() == candidate.lower():
                    col = field
                    break
            if col:
                break

        if not col:
            print(f"No usable path column found in CSV. Columns: {reader.fieldnames}")
            sys.exit(1)

        for row in reader:
            src = row[col].strip()

            if not src:
                skipped += 1
                continue

            if not os.path.exists(src):
                missing += 1
                continue

            dest = os.path.join(QUAR, os.path.basename(src))

            try:
                shutil.move(src, dest)
                moved += 1
            except Exception as e:
                print(f"Error moving {src}: {e}")

    print("=== GEMINI DELETE EXECUTION COMPLETE ===")
    print(f"Moved to quarantine: {moved}")
    print(f"Skipped (no delete_path): {skipped}")
    print(f"Missing files: {missing}")
    print(f"Quarantine: {QUAR}")
    print("========================================")

if __name__ == "__main__":
    main()
