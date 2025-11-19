#!/usr/bin/env python3
import csv
import os
import shutil
import sys
import time
from pathlib import Path

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------
KEEPS_CSV = "artifacts/reports/global_keeps.csv"
DEFAULT_DEST = "/Volumes/dotad/NEW_MUSIC"
MIN_FREE_GB = 5  # if less than this → warn
# --------------------------------------------------------------------

def bytes_free(path: Path) -> int:
    """Return free bytes on filesystem containing path."""
    stat = shutil.disk_usage(str(path))
    return stat.free

def format_gb(b):
    return f"{b / (1024**3):.2f} GB"

def choose_new_destination():
    print("\n>>> Destination volume is low on space.")
    print(">>> Please enter a NEW destination path (must be a mounted volume):")
    while True:
        new = input("New destination directory: ").strip()
        if not new:
            print("Please enter a valid path.")
            continue
        p = Path(new)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception as e:
            print(f"Could not use this path: {e}")

def compute_relative(src_path: Path) -> Path:
    """Try to preserve MUSIC-relative structure when possible."""
    parts = src_path.parts
    if "MUSIC" in parts:
        idx = parts.index("MUSIC")
        return Path(*parts[idx+1:])
    else:
        # fallback: file name only
        return Path(src_path.name)

def main():
    keeps_file = Path(KEEPS_CSV)
    if not keeps_file.is_file():
        print(f"ERROR: KEPT CSV not found: {keeps_file}")
        sys.exit(1)

    dest = Path(DEFAULT_DEST)
    dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    skipped = 0
    missing = 0

    print("\n=== BUILD NEW MUSIC LIBRARY ===")
    print(f"Using keeps file: {KEEPS_CSV}")
    print(f"Initial destination: {dest}")
    print("Resumable mode: enabled\n")

    # Load all paths first (for resumability)
    with open(KEEPS_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        entries = [row["path"] for row in reader if row.get("path")]

    total = len(entries)
    print(f"Total keep entries: {total}\n")

    for i, src in enumerate(entries, start=1):
        src = src.strip().strip('"')
        src_path = Path(src)

        # Progress indicator
        print(f"[{i}/{total}] {src}")

        if not src_path.is_file():
            missing += 1
            print("  MISSING → skipped")
            continue

        # Check free space
        free_bytes = bytes_free(dest)
        if free_bytes < MIN_FREE_GB * (1024**3):
            print(f"\nWARNING: Free space low on {dest}")
            print(f"Remaining: {format_gb(free_bytes)}")
            dest = choose_new_destination()
            print(f"Switched destination to: {dest}\n")

        # Compute relative structure
        rel = compute_relative(src_path)
        out_path = dest / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Resumability: skip if already copied
        if out_path.is_file():
            skipped += 1
            print("  Already exists → skipped")
            continue

        # Perform copy
        try:
            shutil.copy2(src_path, out_path)
            copied += 1
            print("  Copied")
        except Exception as e:
            print(f"  ERROR copying: {e}")

    print("\n=== SUMMARY ===")
    print(f"Copied: {copied}")
    print(f"Skipped: {skipped}")
    print(f"Missing: {missing}")
    print("================\n")

if __name__ == "__main__":
    main()
