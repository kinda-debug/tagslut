#!/usr/bin/env python3
"""
Find 100% exact audio duplicates by decoded stream hash (AUDIO-MD5).

Scans a directory, hashes all audio files by decoded content,
and stores results in a persistent SQLite database for reuse.

Can scan multiple directories (MUSIC, Quarantine, etc.) and
deduplicate across the entire library.

Resumable: Uses JSON cache for current scan, SQLite for historical data.
Interruptible: Ctrl+C saves progress and can resume.

Usage:
    # First scan
    python3 scripts/find_exact_dupes.py /Volumes/dotad/Quarantine \
        --output /tmp/dupes_quarantine.csv

    # Scan MUSIC library
    python3 scripts/find_exact_dupes.py /Volumes/dotad/MUSIC \
        --output /tmp/dupes_music.csv

    # Cross-library deduplication report (from DB)
    python3 scripts/find_exact_dupes.py --report /tmp/cross_dupes.csv
"""

import argparse
import csv
import json
import signal
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav",
    ".aif", ".aiff", ".aifc", ".ogg", ".opus",
    ".wma", ".mka", ".mkv", ".alac"
}

DB_PATH = Path.home() / ".cache" / "exact_dupes.db"
CACHE_PATH = Path.home() / ".cache" / "exact_dupes_current.json"

# Global state for graceful shutdown
interrupted = False


def signal_handler(_signum: int, _frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    global interrupted
    msg = "Interrupt received. Saving checkpoint..."
    print(f"\n[INFO] {msg}", file=sys.stderr)
    interrupted = True


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Initialize or open SQLite database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables if not exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_hashes (
            file_path TEXT PRIMARY KEY,
            audio_hash TEXT NOT NULL,
            file_size INTEGER,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hash ON file_hashes(audio_hash)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            directory TEXT,
            file_count INTEGER,
            scanned_count INTEGER,
            scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def load_cache(cache_path: Path = CACHE_PATH) -> Dict[str, str]:
    """Load previously hashed files from temporary cache."""
    if cache_path.exists():
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cache(
    hash_map: Dict[str, str],
    cache_path: Path = CACHE_PATH
) -> None:
    """Save hashed files to temporary cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(hash_map, f, indent=2)


def audio_md5(path: Path) -> str | None:
    """
    Hash decoded audio stream using FFmpeg's MD5 output.

    Returns MD5 string or None if hash failed.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v", "error",
                "-i", str(path),
                "-f", "md5",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,  # Increased to 2 minutes for large files
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            # Output format: "MD5=abc123def456..."
            lines = result.stdout.strip().split("\n")
            for line in lines:
                if line.startswith("MD5="):
                    return line[4:]
        elif result.returncode != 0:
            err_short = result.stderr[:80] if result.stderr else ""
            if err_short:
                print(f"  ⚠️ FFmpeg error for {path.name}: {err_short}",
                      file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Timeout hashing {path.name} (skipping)", file=sys.stderr)
        return None
    except (OSError, Exception) as e:
        msg = f"Error hashing {path.name}: {e}"
        print(f"  ⚠️ {msg}", file=sys.stderr)
        return None


def scan_directory(
    root: Path,
    conn: sqlite3.Connection,
    verbose: bool = False
) -> Dict[str, List[Path]]:
    """
    Scan directory for audio files, hash them, store in DB and return map.

    Returns hash -> [files] map. Updates SQLite DB with results.
    Uses temporary JSON cache for resumability during current scan.
    """
    global interrupted

    # Load temporary cache (for resume within this scan)
    temp_cache: Dict[str, str] = load_cache()
    cursor = conn.cursor()

    hash_map: Dict[str, List[Path]] = defaultdict(list)
    audio_files: list[Path] = []

    # Find all audio files
    for ext in AUDIO_EXTS:
        audio_files.extend(root.rglob(f"*{ext}"))

    count_msg = f"Found {len(audio_files)} audio files to hash"
    print(f"[INFO] {count_msg}", file=sys.stderr)
    cached_count = len(temp_cache)
    print(f"[INFO] Loaded {cached_count} from temp cache",
          file=sys.stderr)

    # Hash each file (resume from temporary checkpoint)
    new_hashes: Dict[str, str] = {}
    for i, file_path in enumerate(audio_files, 1):
        if interrupted:
            print("[INFO] Scan interrupted", file=sys.stderr)
            break

        file_str = str(file_path)
        if file_str in temp_cache:
            # Use cached hash
            file_hash = temp_cache[file_str]
            hash_map[file_hash].append(file_path)
        else:
            # Compute new hash
            if verbose:
                msg = f"Hashing {file_path.name}..."
                print(f"[{i}/{len(audio_files)}] {msg}", file=sys.stderr)
            else:
                print(f"[{i}/{len(audio_files)}]", end="\r", file=sys.stderr)

            computed_hash = audio_md5(file_path)
            if computed_hash:
                new_hashes[file_str] = computed_hash
                hash_map[computed_hash].append(file_path)

        # Periodically save temp cache and DB (every 50 new files)
        if new_hashes and len(new_hashes) % 50 == 0:
            combined = {**temp_cache, **new_hashes}
            save_cache(combined)

            # Also update DB
            for file_str, file_hash in new_hashes.items():
                try:
                    file_size = Path(file_str).stat().st_size
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO file_hashes
                        (file_path, audio_hash, file_size)
                        VALUES (?, ?, ?)
                        """,
                        (file_str, file_hash, file_size)
                    )
                except OSError:
                    pass

            conn.commit()

    # Final cache and DB save
    if new_hashes:
        combined = {**temp_cache, **new_hashes}
        save_cache(combined)

        for file_str, file_hash in new_hashes.items():
            try:
                file_size = Path(file_str).stat().st_size
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO file_hashes
                    (file_path, audio_hash, file_size)
                    VALUES (?, ?, ?)
                    """,
                    (file_str, file_hash, file_size)
                )
            except OSError:
                pass

        conn.commit()

        # Record scan session
        cursor.execute(
            """
            INSERT INTO scan_sessions (directory, file_count, scanned_count)
            VALUES (?, ?, ?)
            """,
            (str(root), len(audio_files), len(new_hashes))
        )
        conn.commit()

    print("", file=sys.stderr)  # Clear progress line
    return hash_map


def report_cross_dupes(
    conn: sqlite3.Connection,
    output_path: Path
) -> None:
    """
    Generate cross-library deduplication report from DB.

    Shows duplicates found across all previously scanned directories.
    """
    cursor = conn.cursor()

    # Find all hashes that appear multiple times in DB
    cursor.execute("""
        SELECT audio_hash, COUNT(*) as count
        FROM file_hashes
        GROUP BY audio_hash
        HAVING count > 1
        ORDER BY count DESC
    """)

    duplicates = {}
    for audio_hash, _ in cursor.fetchall():
        cursor.execute(
            "SELECT file_path FROM file_hashes WHERE audio_hash = ?",
            (audio_hash,)
        )
        paths = [Path(row[0]) for row in cursor.fetchall()]
        duplicates[audio_hash] = paths

    # Write report
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["hash", "count", "keeper_path", "duplicate_paths"]
        )

        for file_hash, paths in duplicates.items():
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([file_hash, len(paths), keeper, dup_paths])

    print(f"[INFO] Cross-library report written to {output_path}",
          file=sys.stderr)

    # Summary
    total_files = len(duplicates)
    total_dupes = sum(len(p) - 1 for p in duplicates.values())
    print("\n=== CROSS-LIBRARY DUPLICATES ===", file=sys.stderr)
    print(f"Duplicate groups: {total_files}", file=sys.stderr)
    print(f"Files to delete: {total_dupes}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Find 100% exact audio duplicates by decoded stream hash. "
            "Stores in DB for cross-library deduplication."
        )
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Directory to scan (optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/exact_dupes.csv"),
        help="Output CSV file",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"SQLite database path (default: {DB_PATH})",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate cross-library report from DB only (no scanning)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Initialize DB
    conn = init_db(args.db)

    # Handle report-only mode
    if args.report:
        report_cross_dupes(conn, args.output)
        conn.close()
        return 0

    # Require directory for scan mode
    if not args.directory:
        parser.error("directory required unless --report is specified")

    if not args.directory.is_dir():
        print(f"❌ Directory not found: {args.directory}", file=sys.stderr)
        return 1

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)

    print(f"[INFO] Scanning {args.directory}...", file=sys.stderr)
    hash_map = scan_directory(args.directory, conn, args.verbose)

    # Find duplicates (hash appears > 1 time)
    duplicates = {
        h: paths for h, paths in hash_map.items()
        if len(paths) > 1
    }

    print(f"[INFO] Found {len(hash_map)} unique hashes in this scan",
          file=sys.stderr)
    dup_count = sum(len(p) - 1 for p in duplicates.values())
    msg = (
        f"Found {len(duplicates)} duplicate groups "
        f"({dup_count} duplicate files in this directory)"
    )
    print(f"[INFO] {msg}", file=sys.stderr)

    # Write CSV report for this scan
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["hash", "count", "keeper_path", "duplicate_paths"]
        )

        sorted_dupes = sorted(
            duplicates.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )
        for file_hash, paths in sorted_dupes:
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow([file_hash, len(paths), keeper, dup_paths])

    print(f"[INFO] Report written to {args.output}", file=sys.stderr)

    # Summary
    print("\n=== SCAN SUMMARY ===", file=sys.stderr)
    print(f"Total unique files: {len(hash_map)}", file=sys.stderr)
    print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
    delete_count = sum(len(p) - 1 for p in duplicates.values())
    print(f"Files to delete: {delete_count}", file=sys.stderr)

    print("[INFO] DB location:", args.db, file=sys.stderr)
    print("[INFO] To generate cross-library report:",
          "python3 scripts/find_exact_dupes.py --report",
          "--output /tmp/cross_dupes.csv", file=sys.stderr)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
