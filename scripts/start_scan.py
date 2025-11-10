#!/usr/bin/env python3
"""
Launch fast scan v2 directly (no terminal blocking).
Daemonizes itself properly using os.fork()
"""

import os
import sys
import subprocess
from pathlib import Path

REPO_DIR = Path("/Users/georgeskhawam/dedupe_repo")
SCAN_DIR = Path("/Volumes/dotad/Quarantine")
OUTPUT_FILE = Path("/tmp/dupes_quarantine_fast.csv")
LOG_FILE = Path("/tmp/scan_fast_v2.log")

# Daemonize
pid = os.fork()
if pid != 0:
    # Parent: print info and exit
    print(f"✓ Fast scan launched in background (PID {pid})")
    print(f"  Log: tail -f {LOG_FILE}")
    print(f"  Results: {OUTPUT_FILE}")
    sys.exit(0)

# Child: detach from terminal and run
os.setsid()
os.chdir("/")
os.umask(0)

# Redirect output
with open(LOG_FILE, "a", encoding="utf-8") as f:
    subprocess.Popen(
        [
            "python3",
            str(REPO_DIR / "scripts" / "find_dupes_fast_v2.py"),
            str(SCAN_DIR),
            "--output", str(OUTPUT_FILE),
            "--verbose"
        ],
        stdout=f,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

sys.exit(0)
