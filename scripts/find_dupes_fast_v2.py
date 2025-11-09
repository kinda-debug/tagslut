#!/usr/bin/env python3
"""
Fast file-MD5 deduplication scanner (file structure, not decoded audio).
Version 2: Uses file-based cache instead of SQLite to avoid locking issues.

Much faster than audio-MD5 (1-2 sec/file vs 5-10 sec/file).
Good for:
- Quick duplicate identification
- Finding exact file copies (byte-for-byte identical)
- Building baseline deduplication

Trade-off: Finds byte-identical files, not audio-equivalent files.

Usage:
    python3 scripts/find_dupes_fast_v2.py /Volumes/dotad/Quarantine \
        --output /tmp/dupes_quarantine_fast.csv
"""

import argparse
import csv
import hashlib
import json
import signal
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav",
    ".aif", ".aiff", ".aifc", ".ogg", ".opus",
    ".wma", ".mka", ".mkv", ".alac"
}

CACHE_PATH = Path.home() / ".cache" / "file_dupes_cache.json"

interrupted = False


def signal_handler(_signum: int, _frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    global interrupted
    msg = "Interrupt received. Saving progress..."
    print(f"\n[INFO] {msg}", file=sys.stderr)
    interrupted = True


def load_cache(cache_path: Path = CACHE_PATH) -> Dict[str, Any]:
    """Load cache from file."""
    if cache_path.exists():
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {"hashes": {}}
        except (json.JSONDecodeError, IOError):
            return {"hashes": {}}
    return {"hashes": {}}


def save_cache(
    cache: Dict[str, Any],
    cache_path: Path = CACHE_PATH
) -> None:
    """Save cache to file."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)


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
    verbose: bool = False
) -> Dict[str, List[Path]]:
    """Scan directory and hash files."""
    global interrupted

    hash_map: Dict[str, List[Path]] = defaultdict(list)
    audio_files: list[Path] = []

    # Find all audio files
    for ext in AUDIO_EXTS:
        audio_files.extend(root.rglob(f"*{ext}"))

    print(f"[INFO] Found {len(audio_files)} audio files", file=sys.stderr)

    # Load cache
    cache = load_cache()
    cached_hashes = cache.get("hashes", {})

    # Hash each file
    for i, file_path in enumerate(audio_files, 1):
        if interrupted:
            print("[INFO] Scan interrupted", file=sys.stderr)
            save_cache(cache)
            break

        file_str = str(file_path)

        if verbose:
            print(f"[{i}/{len(audio_files)}] {file_path.name}...",
                  file=sys.stderr)
        else:
            print(f"[{i}/{len(audio_files)}]", end="\r", file=sys.stderr)

        # Check cache first
        if file_str in cached_hashes:
            file_hash = cached_hashes[file_str]
        else:
            file_hash = file_md5(file_path)
            if file_hash:
                cached_hashes[file_str] = file_hash

        if file_hash:
            hash_map[file_hash].append(file_path)

        # Save cache every 100 files
        if i % 100 == 0:
            cache["hashes"] = cached_hashes
            save_cache(cache)

    # Final save
    cache["hashes"] = cached_hashes
    save_cache(cache)
    print("", file=sys.stderr)
    return hash_map


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fast file-MD5 deduplication scanner"
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        help="Directory to scan",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/dupes_quarantine_fast.csv"),
        help="Output CSV path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show each filename",
    )

    args = parser.parse_args()

    if not args.directory:
        parser.error("directory required")

    if not args.directory.is_dir():
        print(f"❌ Directory not found: {args.directory}", file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, signal_handler)

    print("[INFO] Fast scan (file MD5, not audio decode)",
          file=sys.stderr)
    print(f"[INFO] Scanning {args.directory}...", file=sys.stderr)

    hash_map = scan_directory(args.directory, args.verbose)

    duplicates = {h: p for h, p in hash_map.items() if len(p) > 1}

    print(f"[INFO] Found {len(duplicates)} duplicate groups",
          file=sys.stderr)

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["md5_hash", "count", "keeper_path", "duplicate_paths"]
        )

        for file_md5_hash, paths in sorted(
            duplicates.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            keeper = paths[0]
            dupes = paths[1:]
            dup_paths = " | ".join(str(p) for p in dupes)
            writer.writerow(
                [file_md5_hash, len(paths), keeper, dup_paths]
            )

    print(f"[INFO] Report written to {args.output}", file=sys.stderr)

    total_dupes = sum(len(p) - 1 for p in duplicates.values())
    print("\n=== SCAN SUMMARY ===", file=sys.stderr)
    print(f"Total files scanned: {len(hash_map)}", file=sys.stderr)
    print(f"Duplicate groups: {len(duplicates)}", file=sys.stderr)
    print(f"Files to delete: {total_dupes}", file=sys.stderr)

    # Calculate space
    print("Estimated space savings: ", end="", file=sys.stderr)
    total_dup_size = 0
    for hash_val, paths in duplicates.items():
        # Size of each duplicate (skip keeper - first one)
        for dupe_path in paths[1:]:
            try:
                total_dup_size += dupe_path.stat().st_size
            except OSError:
                pass

    if total_dup_size > 0:
        size_gb = total_dup_size / (1024 ** 3)
        print(f"{size_gb:.2f} GB", file=sys.stderr)
    else:
        print("0 GB", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
