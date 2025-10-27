#!/usr/bin/env python3
"""Run the full deduplication workflow: scan, repair, dedupe."""

import subprocess
import sys
from pathlib import Path


def main():
    root = "/Volumes/dotad/MUSIC"  # or pass as arg

    # Step 1: Scan
    print("Step 1: Scanning files...")
    cmd = [sys.executable, "scan_flac_db.py"]
    result = subprocess.run(cmd, check=True)
    if result.returncode != 0:
        print("Scan failed")
        sys.exit(1)

    # Check for broken files
    broken_playlist = Path(root) / "broken_files_unrepaired.m3u"
    if broken_playlist.exists() and broken_playlist.read_text().strip():
        print("Step 2: Repairing broken files...")
        cmd = [sys.executable, "repair_flacs.py"]
        result = subprocess.run(cmd, check=True)
        if result.returncode != 0:
            print("Repair failed")
            sys.exit(1)
    else:
        print("No broken files to repair.")

    # Step 3: Dedupe
    print("Step 3: Deduplicating...")
    cmd = [sys.executable, "dd_flac_dedupe_db.py", "--root", root,
           "--commit", "--verbose"]
    result = subprocess.run(cmd, check=True)
    if result.returncode != 0:
        print("Deduplication failed")
        sys.exit(1)

    print("Workflow completed successfully!")


if __name__ == "__main__":
    main()
