from __future__ import annotations
import os
import shutil
from pathlib import Path

def undo_quarantine(quarantine_root):
    q_root = Path(quarantine_root)
    if not q_root.exists():
        print(f"Error: {quarantine_root} not found.")
        return

    print(f"Restoring files from {q_root}...")

    # Files were moved using: dest = quarantine_root / rel_path
    # where rel_path starts after /Volumes/ or from root

    success = 0
    errors = 0

    # Use os.walk to find all files in quarantine
    for root, dirs, files in os.walk(q_root):
        for name in files:
            src = Path(root) / name
            rel_path = src.relative_to(q_root)

            # Reconstruct original path.
            # If the first part of rel_path matches a mounted volume, it's /Volumes/Part1/...
            target_path = Path("/Volumes") / rel_path

            if not target_path.parent.exists():
                try:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    print(f"Error creating directory {target_path.parent}: {e}")
                    errors += 1
                    continue

            try:
                shutil.move(str(src), str(target_path))
                success += 1
                if success % 100 == 0:
                    print(f"Restored {success} files...")
            except Exception as e:
                print(f"Error restoring {src} to {target_path}: {e}")
                errors += 1

    print(f"\nFinished: {success} restored, {errors} errors.")

if __name__ == "__main__":
    # Run for both detected quarantine folders
    undo_quarantine("/Volumes/COMMUNE/M/_quarantine/DEDUPE_20260120_001744")
    undo_quarantine("/Volumes/COMMUNE/M/_quarantine/DEDUPE_20260120_002431")
