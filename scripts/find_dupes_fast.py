#!/usr/bin/env python3
"""
Fast file-MD5 deduplication scanner (file structure, not decoded audio).

Much faster than audio-MD5 (1-2 sec/file vs 5-10 sec/file).
Good for:
- Quick duplicate identification
- Finding exact file copies (byte-for-byte identical)
- Building baseline deduplication

Trade-off: Finds byte-identical files, not audio-equivalent files.
So different file formats/bitrates of same song won't match.

Usage:
    python3 scripts/find_dupes_fast.py /Volumes/dotad/Quarantine \
        --output /tmp/dupes_quarantine_fast.csv
"""

import argparse
import csv
import hashlib
import signal
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav",
    ".aif", ".aiff", ".aifc", ".ogg", ".opus",
    ".wma", ".mka", ".mkv", ".alac"
}

DB_PATH = Path.home() / ".cache" / "file_dupes.db"

interrupted = False


def signal_handler(_signum: int, _frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    global interrupted
    msg = "Interrupt received. Saving progress..."
    print(f"\n[INFO] {msg}", file=sys.stderr)
    interrupted = True


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)  # 30 second timeout
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            file_path TEXT PRIMARY KEY,
            file_md5 TEXT NOT NULL,
            file_size INTEGER,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_md5
        ON file_hashes(file_md5)
    """)

    conn.commit()
    return conn


def file_md5(path: Path) -> str | None:
    """
    Calculate MD5 hash of file (not decoded audio).
    Much faster than audio decode hashing.
    """
    try:
        md5_hash = hashlib.md5()
        with open(path, "rb") as f:
            # Read in 64KB chunks for efficiency
            for chunk in iter(lambda: f.read(65536), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except (OSError, Exception) as e:
        print(f"  ⚠️  Error hashing {path.name}: {e}", file=sys.stderr)
        return None


def scan_directory(
    root: Path,
    conn: sqlite3.Connection,
    verbose: bool = False
) -> Dict[str, List[Path]]:
    """Scan directory and hash files."""
    global interrupted

    cursor = conn.cursor()
    hash_map: Dict[str, List[Path]] = defaultdict(list)
    audio_files: list[Path] = []

    # Find all audio files
    for ext in AUDIO_EXTS:
        audio_files.extend(root.rglob(f"*{ext}"))

    print(f"[INFO] Found {len(audio_files)} audio files", file=sys.stderr)

    # Hash each file
    for i, file_path in enumerate(audio_files, 1):
        if interrupted:
            print("[INFO] Scan interrupted", file=sys.stderr)
            break

        file_str = str(file_path)

        if verbose:
            print(f"[{i}/{len(audio_files)}] {file_path.name}...",
                  file=sys.stderr)
        else:
            print(f"[{i}/{len(audio_files)}]", end="\r", file=sys.stderr)

        file_hash = file_md5(file_path)
        if file_hash:
            hash_map[file_hash].append(file_path)
            try:
                file_size = file_path.stat().st_size
                retries = 3
                while retries > 0:
                    try:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO file_hashes
                            (file_path, file_md5, file_size)
                            VALUES (?, ?, ?)
                            """,
                            (file_str, file_hash, file_size)
                        )
                        break
                    except sqlite3.OperationalError as e:
                        if "database is locked" in str(e) and retries > 1:
                            retries -= 1
                            time.sleep(0.5)
                        else:
                            raise
            except (OSError, sqlite3.OperationalError):
                pass

        # Save every 100 files
        if i % 100 == 0:
            conn.commit()

    conn.commit()
    print("", file=sys.stderr)
    return hash_map


def report_cross_dupes(
    conn: sqlite3.Connection,
    output_path: Path
) -> None:
    """Generate deduplication report from DB."""
    cursor = conn.cursor()

    cursor.execute("""
        SELECT file_md5, COUNT(*) as count
        FROM file_hashes
        GROUP BY file_md5
        HAVING count > 1
        ORDER BY count DESC
    """)

    duplicates = {}
    for file_md5, _ in cursor.fetchall():
        cursor.execute(
            "SELECT file_path FROM file_hashes WHERE file_md5 = ?",
            (file_md5,)
        )
        paths = [Path(row[0]) for row in cursor.fetchall()]
        duplicates[file_md5] = paths

    # Write report
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["md5_hash", "count", "keeper_path", "duplicate_paths"]
        )

        for file_md5, paths in sorted(duplicates.items()):
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([file_md5, len(paths), keeper, dup_paths])

    print(f"[INFO] Report written to {output_path}", file=sys.stderr)

    # Summary
    total_dupes = sum(len(p) - 1 for p in duplicates.values())
    print("\n=== SCAN SUMMARY ===", file=sys.stderr)
    print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
    print(f"Files to delete: {total_dupes}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fast file-MD5 deduplication (byte-identical files)"
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Directory to scan",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/file_dupes.csv"),
        help="Output CSV file",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="SQLite database path",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate report from DB only",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show each filename",
    )

    args = parser.parse_args()

    conn = init_db(args.db)

    if args.report:
        report_cross_dupes(conn, args.output)
        conn.close()
        return 0

    if not args.directory:
        parser.error("directory required unless --report is specified")

    if not args.directory.is_dir():
        print(f"❌ Directory not found: {args.directory}", file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, signal_handler)

    print("[INFO] Fast scan (file MD5, not audio decode)",
          file=sys.stderr)
    print(f"[INFO] Scanning {args.directory}...", file=sys.stderr)

    hash_map = scan_directory(args.directory, conn, args.verbose)

    duplicates = {h: p for h, p in hash_map.items() if len(p) > 1}

    print(f"[INFO] Found {len(duplicates)} duplicate groups",
          file=sys.stderr)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["md5_hash", "count", "keeper_path", "duplicate_paths"]
        )

        for file_md5, paths in sorted(
            duplicates.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([file_md5, len(paths), keeper, dup_paths])

    print(f"[INFO] Report written to {args.output}", file=sys.stderr)

    total_dupes = sum(len(p) - 1 for p in duplicates.values())
    print("\n=== SCAN SUMMARY ===", file=sys.stderr)
    print(f"Total files scanned: {len(hash_map)}", file=sys.stderr)
    print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
    print(f"Files to delete: {total_dupes}", file=sys.stderr)
    print("Estimated space savings: ", end="", file=sys.stderr)

    # Calculate space
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(file_size)
        FROM (
            SELECT file_size, row_number()
                OVER (PARTITION BY file_md5 ORDER BY file_path)
                as rn
            FROM file_hashes
        )
        WHERE rn > 1
    """)
    result = cursor.fetchone()
    if result and result[0]:
        size_gb = result[0] / (1024 ** 3)
        print(f"{size_gb:.2f} GB", file=sys.stderr)
    else:
        print("0 GB", file=sys.stderr)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
