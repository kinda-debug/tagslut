#!/usr/bin/env python3
import csv
import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "artifacts" / "db" / "library.db"
OUT_CSV = REPO_ROOT / "artifacts" / "reports" / "best_copy_decisions.csv"

# Roots we care about
NEW_LIBRARY_ROOT = "/Volumes/dotad/NEW_LIBRARY"
VAULT_ROOT = "/Volumes/Vault"
BAD_ROOT = "/Volumes/Bad"
SAD_ROOT = "/Volumes/sad"

# Only these are excluded as known-bad
EXCLUDE_SUBSTRINGS = [
    "/_quarantine_bad_flacs/",
    "/_quarantine_bad_mp3s/",
]


def is_candidate(path: str) -> bool:
    """Select files from the main roots, excluding obvious garbage."""
    if not (
        path.startswith(NEW_LIBRARY_ROOT)
        or path.startswith(VAULT_ROOT)
        or path.startswith(BAD_ROOT)
        or path.startswith(SAD_ROOT)
    ):
        return False
    for bad in EXCLUDE_SUBSTRINGS:
        if bad in path:
            return False
    return True


def extension(path: str) -> str:
    name = os.path.basename(path)
    if "." in name:
        return name.rsplit(".", 1)[1].lower()
    return ""


def is_ignored_format(path: str) -> bool:
    """Only ignore MP3; everything else competes equally."""
    return extension(path) == "mp3"


def main() -> None:
    os.makedirs(OUT_CSV.parent, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT path, COALESCE(duration, 0.0) AS duration
            FROM library_files
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    # Filter and group by basename stem (case-insensitive, no extension)
    groups = {}
    for path, duration in rows:
        if not is_candidate(path):
            continue
        if is_ignored_format(path):
            continue

        name = os.path.basename(path).lower()
        stem = name.rsplit(".", 1)[0]  # basename without extension

        groups.setdefault(stem, []).append((path, float(duration)))

    # (base_name, path, duration, decision)
    decisions = []

    for base_name, entries in groups.items():
        # entries: list[(path, duration)]
        ranked = sorted(
            entries,
            key=lambda pd: (
                -pd[1],  # longer duration first
                pd[0],   # deterministic tie-breaker
            ),
        )
        keep_path, keep_duration = ranked[0]
        decisions.append((base_name, keep_path, keep_duration, "keep"))
        for path, duration in ranked[1:]:
            decisions.append((base_name, path, duration, "move"))

    # Write CSV
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["base_name", "path", "duration", "decision"])
        for row in decisions:
            writer.writerow(row)

    print(f"Wrote {len(decisions)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()