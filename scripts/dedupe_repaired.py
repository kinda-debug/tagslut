#!/usr/bin/env python3
"""Find content duplicates inside a repaired staging directory (name-independent).

Outputs a CSV with groups of files that share the same PCM SHA1. Default is read-only.

Usage:
  # Normal mode (scans all files, slower):
  python3 -m scripts.dedupe_repaired --repaired /path/to/ReallyRepaired \
      --out repaired_dupes.csv [--limit 200] [--quarantine /path] [--move]

  # Fast mode (size-first optimization, recommended for large trees):
  python3 -m scripts.dedupe_repaired --repaired /path/to/ReallyRepaired \
      --out repaired_dupes.csv --fast [--quarantine /path] [--move]

If --move is set, duplicates (all but the first in each group) are moved to the quarantine dir.

Modes:
  - Default: Compute PCM SHA1 for all FLAC files (slower, comprehensive)
  - --fast: Index by file size first, only hash files with same size (faster)
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
import subprocess
from pathlib import Path
from collections import defaultdict

try:
    from scripts.lib.common import compute_pcm_sha1
except Exception:
    compute_pcm_sha1 = None


def ffprobe_duration(path: Path):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ], stderr=subprocess.DEVNULL)
        return float(out.decode().strip())
    except Exception:
        return None


def dedupe_fast_mode(
    repaired_root: Path,
    limit: int = 0
) -> list[tuple[str, list[str]]]:
    """Fast size-first deduplication (sizefirst algorithm)."""
    # Build size index
    size_index: dict[int, list[Path]] = defaultdict(list)
    print("Indexing sizes in repaired tree...")
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            pth = Path(root) / name
            try:
                sz = pth.stat().st_size
                size_index[sz].append(pth)
            except Exception:
                continue

    # Keep only buckets with more than 1 file
    candidate_buckets = {
        sz: paths for sz, paths in size_index.items() if len(paths) > 1
    }
    print(
        f"Found {len(candidate_buckets)} size-buckets with potential "
        f"duplicates (out of {len(size_index)} sizes)"
    )

    groups = []  # list of (hash, [paths])
    buckets_checked = 0
    for sz, paths in sorted(candidate_buckets.items(), key=lambda t: -len(t[1])):
        buckets_checked += 1
        if limit and buckets_checked > limit:
            break
        # compute hashes for all files in this bucket
        hash_map: dict[str, list[str]] = defaultdict(list)
        for p in paths:
            try:
                h = compute_pcm_sha1(p)
            except Exception:
                h = None
            if h is None:
                continue
            hash_map[h].append(str(p))
        for h, lst in hash_map.items():
            if len(lst) > 1:
                groups.append((h, lst))
    
    print(
        f"Checked {buckets_checked} candidate buckets; "
        f"found {len(groups)} duplicate groups"
    )
    return groups


def dedupe_normal_mode(
    repaired_root: Path,
    limit: int = 0
) -> list[tuple[str, list[str]]]:
    """Normal mode: scan all files and compute PCM SHA1."""
    hashes: dict[str, list[str]] = defaultdict(list)
    checked = 0
    
    print("Scanning all FLAC files...")
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            path = Path(root) / name
            try:
                path.stat().st_size
            except Exception:
                continue
            # compute PCM SHA1
            h = compute_pcm_sha1(path)
            if h:
                hashes[h].append(str(path))
            checked += 1
            if limit and checked >= limit:
                break
        if limit and checked >= limit:
            break

    # build groups where hash has multiple entries
    groups = [(h, paths) for h, paths in hashes.items() if len(paths) > 1]
    groups.sort(key=lambda t: (-len(t[1]), t[0]))
    
    print(f"Checked {checked} files; found {len(groups)} duplicate groups")
    return groups


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--repaired", required=True, help="Repaired staging directory")
    p.add_argument("--out", default="repaired_dupes.csv", help="Output CSV path")
    p.add_argument(
        "--fast",
        action="store_true",
        help="Use size-first optimization (faster for large trees)"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit files/buckets (0 = unlimited)"
    )
    p.add_argument(
        "--quarantine",
        default=None,
        help="Directory to move duplicates into when --move is set"
    )
    p.add_argument(
        "--move",
        action="store_true",
        help="Move duplicate files (all but keeper) to quarantine"
    )
    args = p.parse_args(argv)

    repaired_root = Path(args.repaired)
    out_csv = Path(args.out)
    
    if not repaired_root.is_dir():
        print(f"ERROR: Repaired root not found: {repaired_root}")
        return 2

    if compute_pcm_sha1 is None:
        print(
            "ERROR: compute_pcm_sha1 not available; "
            "run with `python -m` inside the repo"
        )
        return 3

    # Run deduplication
    if args.fast:
        groups = dedupe_fast_mode(repaired_root, args.limit)
    else:
        groups = dedupe_normal_mode(repaired_root, args.limit)

    # Write CSV
    with out_csv.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['pcm_hash', 'count', 'paths'])
        writer.writeheader()
        for h, paths in groups:
            writer.writerow({
                'pcm_hash': h,
                'count': len(paths),
                'paths': ' | '.join(paths)
            })

    print(f"Wrote {out_csv}")

    # Optional: move duplicates
    if args.move:
        if args.quarantine is None:
            print("ERROR: --move requires --quarantine to be set")
            return 4
        qroot = Path(args.quarantine)
        qroot.mkdir(parents=True, exist_ok=True)
        moved = 0
        for h, paths in groups:
            # Keeper selection: prefer path without '.repaired' suffix
            keeper = None
            for p in paths:
                if '.repaired' not in p:
                    keeper = p
                    break
            if keeper is None:
                keeper = paths[0]
            
            for p in paths:
                if p == keeper:
                    continue
                src = Path(p)
                dest = qroot / src.name
                # avoid overwriting existing quarantine files
                if dest.exists():
                    suffix_ts = int(dest.stat().st_mtime)
                    dest = dest.with_name(
                        dest.stem + '_' + str(suffix_ts) + dest.suffix
                    )
                try:
                    src.rename(dest)
                    moved += 1
                except Exception as e:
                    print(f"WARNING: Failed to move {src} -> {dest}: {e}")
        print(f"Moved {moved} duplicate files to {qroot}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
