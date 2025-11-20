#!/usr/bin/env python3
"""
merge_new_music_into_music.py

Final-stage merge of the cleaned /Volumes/dotad/NEW_MUSIC tree
into /Volumes/dotad/MUSIC.

Behaviour:
- Uses artifacts/db/library.db (library_files table).
- Reads all FLAC files under src_root (/Volumes/dotad/NEW_MUSIC by default).
- Derives a "clean" destination path under dest_root (/Volumes/dotad/MUSIC)
  by stripping container directories from the front of the relative path:
    - First-level containers:  NEW_LIBRARY, Vault, RECOVERED_TRASH, Garbage copy
    - Second-level containers: MUSIC, RECOVERED_TRASH, Garbage copy, Vault
- Uses checksum-based dedupe:
    * If dest path exists and checksum is identical: skip + log.
    * If dest path exists and checksum differs: skip + log conflict.
    * If another file in MUSIC already has the same checksum: skip + log.
- Only copies .flac (case-insensitive).
- Never overwrites existing files.
- Logs all decisions to a CSV.

Usage:
    python3 merge_new_music_into_music.py \
        --db artifacts/db/library.db \
        --src-root /Volumes/dotad/NEW_MUSIC \
        --dest-root /Volumes/dotad/MUSIC \
        --log artifacts/reports/new_music_to_music_merge_log.csv
"""

import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple


# Container-like directories to strip from the *front* of the relative path
FIRST_LEVEL_CONTAINERS = {
    "NEW_LIBRARY",
    "Vault",
    "RECOVERED_TRASH",
    "Garbage copy",
}

SECOND_LEVEL_CONTAINERS = {
    "MUSIC",
    "RECOVERED_TRASH",
    "Garbage copy",
    "Vault",
}


def debug(msg: str) -> None:
    """Lightweight debug printing."""
    print(msg, file=sys.stderr)


def load_rows_for_prefix(
    conn: sqlite3.Connection, prefix: str
) -> List[sqlite3.Row]:
    """
    Load all library_files rows whose path starts with prefix.
    prefix must be an absolute path like '/Volumes/dotad/NEW_MUSIC'.
    """
    prefix = prefix.rstrip("/")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT path, checksum
        FROM library_files
        WHERE path LIKE ? || '/%'
        ORDER BY path
        """,
        (prefix,),
    )
    return cur.fetchall()


def build_dest_indexes(
    dest_rows: List[sqlite3.Row]
) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Build:
      - path_to_checksum for dest_root
      - checksum_to_paths for dest_root
    """
    path_to_checksum: Dict[str, str] = {}
    checksum_to_paths: Dict[str, List[str]] = {}

    for row in dest_rows:
        path = row["path"]
        checksum = row["checksum"]
        if checksum is None:
            continue
        path_to_checksum[path] = checksum
        checksum_to_paths.setdefault(checksum, []).append(path)

    return path_to_checksum, checksum_to_paths


def strip_containers(rel_parts: List[str]) -> List[str]:
    """
    Given the parts of a path relative to src_root, strip container dirs
    from the *front*:

      1) While the first element is in FIRST_LEVEL_CONTAINERS, drop it.
      2) While the first element is in SECOND_LEVEL_CONTAINERS, drop it.

    This is intentionally conservative: it only touches leading components.
    """
    parts = list(rel_parts)

    # Strip "first-level" containers (e.g. NEW_LIBRARY, Vault)
    while parts and parts[0] in FIRST_LEVEL_CONTAINERS:
        parts.pop(0)

    # Strip immediate secondary containers (MUSIC, RECOVERED_TRASH, etc.)
    while parts and parts[0] in SECOND_LEVEL_CONTAINERS:
        parts.pop(0)

    return parts


def ensure_parent_dir(path: Path) -> None:
    """Ensure parent directory exists for a path."""
    parent = path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge /Volumes/dotad/NEW_MUSIC into /Volumes/dotad/MUSIC in a clean way."
    )
    parser.add_argument(
        "--db",
        default="artifacts/db/library.db",
        help="Path to library.db (default: artifacts/db/library.db)",
    )
    parser.add_argument(
        "--src-root",
        default="/Volumes/dotad/NEW_MUSIC",
        help="Source root (default: /Volumes/dotad/NEW_MUSIC)",
    )
    parser.add_argument(
        "--dest-root",
        default="/Volumes/dotad/MUSIC",
        help="Destination root (default: /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--log",
        default="artifacts/reports/new_music_to_music_merge_log.csv",
        help="CSV log path (default: artifacts/reports/new_music_to_music_merge_log.csv)",
    )

    args = parser.parse_args()

    db_path = Path(args.db)
    src_root = Path(args.src_root)
    dest_root = Path(args.dest_root)
    log_path = Path(args.log)

    print("=== MERGE NEW_MUSIC INTO MUSIC ===")
    print("DB:        ", db_path)
    print("SRC ROOT:  ", src_root)
    print("DEST ROOT: ", dest_root)
    print("LOG CSV:   ", log_path)

    if not db_path.is_file():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    if not src_root.is_dir():
        print(f"ERROR: src_root does not exist or is not a directory: {src_root}", file=sys.stderr)
        sys.exit(1)

    if not dest_root.exists():
        print(f"Destination root does not exist; creating: {dest_root}")
        dest_root.mkdir(parents=True, exist_ok=True)

    # Ensure log directory exists
    if not log_path.parent.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    print("Loading library_files rows for src_root...")
    src_rows = load_rows_for_prefix(conn, str(src_root))
    print(f"  Loaded {len(src_rows)} rows under src_root.")

    print("Loading library_files rows for dest_root...")
    dest_rows = load_rows_for_prefix(conn, str(dest_root))
    print(f"  Loaded {len(dest_rows)} rows under dest_root.")

    path_to_checksum_dest, checksum_to_dest_paths = build_dest_indexes(dest_rows)
    print(f"  Dest path index size: {len(path_to_checksum_dest)}")
    print(f"  Unique dest checksums: {len(checksum_to_dest_paths)}")

    total_src = 0
    copied = 0
    skipped_same_checksum_dest = 0
    skipped_same_checksum_elsewhere = 0
    skipped_diff_checksum_conflict = 0
    skipped_missing_src = 0
    skipped_not_flac = 0
    skipped_empty_rel = 0
    errors = 0

    # Prepare logging
    with log_path.open("w", newline="", encoding="utf-8") as f_log:
        writer = csv.writer(f_log)
        writer.writerow(
            [
                "src_path",
                "dest_path",
                "action",
                "reason",
                "checksum",
            ]
        )

        for row in src_rows:
            src_path_str = row["path"]
            checksum = row["checksum"]

            # Only care about FLAC files on disk
            if not src_path_str.lower().endswith(".flac"):
                skipped_not_flac += 1
                writer.writerow(
                    [src_path_str, "", "SKIP_NOT_FLAC", "Not a .flac extension", checksum]
                )
                continue

            src_path = Path(src_path_str)

            if not src_path.is_file():
                skipped_missing_src += 1
                writer.writerow(
                    [src_path_str, "", "SKIP_SRC_MISSING", "Source file does not exist", checksum]
                )
                continue

            try:
                rel = src_path.relative_to(src_root)
            except ValueError:
                # Not actually under src_root; skip defensively
                skipped_empty_rel += 1
                writer.writerow(
                    [
                        src_path_str,
                        "",
                        "SKIP_NOT_UNDER_SRC_ROOT",
                        "Path not under src_root",
                        checksum,
                    ]
                )
                continue

            rel_parts = list(rel.parts)
            clean_parts = strip_containers(rel_parts)

            if not clean_parts:
                skipped_empty_rel += 1
                writer.writerow(
                    [
                        src_path_str,
                        "",
                        "SKIP_EMPTY_REL",
                        "No path left after stripping containers",
                        checksum,
                    ]
                )
                continue

            dest_path = dest_root.joinpath(*clean_parts)
            dest_path_str = str(dest_path)

            total_src += 1
            if total_src % 500 == 0:
                debug(f"Processed {total_src} source files...")

            # Case 1: destination path already exists
            if dest_path.exists():
                # Use DB knowledge if we have it
                dest_ck = path_to_checksum_dest.get(dest_path_str)

                if checksum is not None and dest_ck == checksum:
                    skipped_same_checksum_dest += 1
                    writer.writerow(
                        [
                            src_path_str,
                            dest_path_str,
                            "SKIP_DEST_EXISTS_SAME_CHECKSUM",
                            "Destination file already exists with same checksum",
                            checksum,
                        ]
                    )
                    continue
                else:
                    skipped_diff_checksum_conflict += 1
                    writer.writerow(
                        [
                            src_path_str,
                            dest_path_str,
                            "SKIP_DEST_EXISTS_DIFF_CHECKSUM",
                            "Destination path exists with different checksum or unknown checksum",
                            checksum,
                        ]
                    )
                    continue

            # Case 2: dest path does not exist, but same checksum already present elsewhere under MUSIC
            if checksum is not None and checksum in checksum_to_dest_paths:
                existing_paths = checksum_to_dest_paths[checksum]
                existing_str = existing_paths[0] if existing_paths else ""
                skipped_same_checksum_elsewhere += 1
                writer.writerow(
                    [
                        src_path_str,
                        existing_str,
                        "SKIP_SAME_CHECKSUM_ELSEWHERE",
                        "Same checksum already present under MUSIC at a different path",
                        checksum,
                    ]
                )
                continue

            # Case 3: need to copy
            try:
                ensure_parent_dir(dest_path)
                # Actual copy
                import shutil

                shutil.copy2(str(src_path), str(dest_path))
                copied += 1
                writer.writerow(
                    [
                        src_path_str,
                        dest_path_str,
                        "COPIED",
                        "",
                        checksum,
                    ]
                )

                # Update dest indexes in-memory so subsequent iterations see this file
                if checksum is not None:
                    path_to_checksum_dest[dest_path_str] = checksum
                    checksum_to_dest_paths.setdefault(checksum, []).append(dest_path_str)

            except OSError as e:
                errors += 1
                writer.writerow(
                    [
                        src_path_str,
                        dest_path_str,
                        "ERROR",
                        f"OSError: {e}",
                        checksum,
                    ]
                )
                print(f"ERROR copying {src_path} -> {dest_path}: {e}", file=sys.stderr)

    print("=== MERGE SUMMARY ===")
    print(f"Total FLAC rows under src_root (from DB): {len(src_rows)}")
    print(f"Total FLAC files considered (on disk):   {total_src}")
    print(f"Copied:                                   {copied}")
    print(f"Skipped (dest exists, same checksum):     {skipped_same_checksum_dest}")
    print(f"Skipped (same checksum elsewhere):        {skipped_same_checksum_elsewhere}")
    print(f"Skipped (dest exists, diff checksum):     {skipped_diff_checksum_conflict}")
    print(f"Skipped (source missing):                 {skipped_missing_src}")
    print(f"Skipped (not flac):                       {skipped_not_flac}")
    print(f"Skipped (empty/invalid relative path):    {skipped_empty_rel}")
    print(f"Errors:                                   {errors}")
    print(f"Log written to:                           {log_path}")
    print("==========================================")


if __name__ == "__main__":
    main()
