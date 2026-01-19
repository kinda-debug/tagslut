from __future__ import annotations
import os
import shutil
import pandas as pd
from pathlib import Path
import argparse

def execute_resolution(report_csv: str, dry_run: bool = True):
    if not os.path.exists(report_csv):
        print(f"Error: {report_csv} not found")
        return

    df = pd.read_csv(report_csv)

    print(f"Executing resolution from {report_csv}")
    print(f"Dry run: {dry_run}")

    counts = {"PROMOTE": 0, "QUARANTINE": 0, "DELETE": 0, "SKIP": 0, "ERROR": 0}

    library_root = Path("/Volumes/COMMUNE/M/Library")
    quarantine_root = Path("/Volumes/COMMUNE/M/_quarantine/suspect_duplicates")
    suspect_root = Path("/Volumes/COMMUNE/M/Suspect")

    for _, row in df.iterrows():
        path = Path(row["path"])
        action = row["action"]

        if not path.exists():
            print(f"File not found, skipping: {path}")
            counts["SKIP"] += 1
            continue

        try:
            if action == "DELETE":
                if dry_run:
                    print(f"[DRY-RUN] Would delete: {path}")
                else:
                    path.unlink()
                counts["DELETE"] += 1

            elif action == "QUARANTINE":
                rel_path = path.relative_to(suspect_root)
                dest = quarantine_root / rel_path
                if dry_run:
                    print(f"[DRY-RUN] Would move to quarantine: {path} -> {dest}")
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dest))
                counts["QUARANTINE"] += 1

            elif action == "PROMOTE":
                # For promotion, we maintain the relative path within the library
                # If it's already in a subfolder like '2026-01-16_corrupt_canonical', we might want to strip that.
                # However, to be safe, we'll keep the relative path from /Suspect
                rel_path = path.relative_to(suspect_root)
                dest = library_root / rel_path
                if dry_run:
                    print(f"[DRY-RUN] Would promote: {path} -> {dest}")
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dest))
                counts["PROMOTE"] += 1
            else:
                counts["SKIP"] += 1
        except Exception as e:
            print(f"Error processing {path}: {e}")
            counts["ERROR"] += 1

    print("\nExecution Summary:")
    for k, v in counts.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="suspect_resolution_report.csv")
    parser.add_argument("--execute", action="store_true", help="Actually move/delete files")
    args = parser.parse_args()

    execute_resolution(args.report, dry_run=not args.execute)
