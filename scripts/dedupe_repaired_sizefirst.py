#!/usr/bin/env python3
"""Faster dedupe for a repaired tree: index by file size first, then compute PCM SHA1
only for size-buckets with >1 file. Outputs CSV of duplicate groups (read-only by default).

Usage:
  python3 -m scripts.dedupe_repaired_sizefirst --repaired /path/to/ReallyRepaired --out repaired_dupes.csv [--move --quarantine /path]
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
from pathlib import Path
import subprocess

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


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--repaired", required=True)
    p.add_argument("--out", default="repaired_dupes_sizefirst.csv")
    p.add_argument("--move", action="store_true")
    p.add_argument("--quarantine", default=None)
    p.add_argument("--limit", type=int, default=0, help="0=all size-buckets")
    args = p.parse_args(argv)

    repaired_root = Path(args.repaired)
    out_csv = Path(args.out)
    if not repaired_root.is_dir():
        print("Repaired root not found:", repaired_root); return 2
    if compute_pcm_sha1 is None:
        print("compute_pcm_sha1 not available from scripts.lib.common; run as module: python -m scripts.dedupe_repaired_sizefirst")
        return 3

    # Build size index
    size_index: dict[int, list[Path]] = {}
    print("Indexing sizes in repaired tree...")
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            pth = Path(root) / name
            try:
                sz = pth.stat().st_size
            except Exception:
                continue
            size_index.setdefault(sz, []).append(pth)

    # Keep only buckets with more than 1 file
    candidate_buckets = {sz: paths for sz, paths in size_index.items() if len(paths) > 1}
    print(f"Found {len(candidate_buckets)} size-buckets with potential duplicates (out of {len(size_index)} sizes)")

    groups = []  # list of (hash, [paths])
    buckets_checked = 0
    for sz, paths in sorted(candidate_buckets.items(), key=lambda t: -len(t[1])):
        buckets_checked += 1
        if args.limit and buckets_checked > args.limit:
            break
        # compute hashes for all files in this bucket
        hash_map: dict[str, list[str]] = {}
        for p in paths:
            try:
                h = compute_pcm_sha1(p)
            except Exception:
                h = None
            if h is None:
                continue
            hash_map.setdefault(h, []).append(str(p))
        for h, lst in hash_map.items():
            if len(lst) > 1:
                groups.append((h, lst))

    # write CSV
    with out_csv.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['pcm_hash','count','paths'])
        writer.writeheader()
        for h, lst in groups:
            writer.writerow({'pcm_hash': h, 'count': len(lst), 'paths': ' | '.join(lst)})

    print(f"Checked {len(candidate_buckets)} candidate buckets; found {len(groups)} duplicate groups. Wrote {out_csv}")

    if args.move:
        if args.quarantine is None:
            print("--move requires --quarantine. Aborting moves.")
            return 4
        qroot = Path(args.quarantine)
        qroot.mkdir(parents=True, exist_ok=True)
        moved = 0
        for h, lst in groups:
            # choose keeper: prefer filename without '.repaired' suffix
            keeper = None
            for p in lst:
                if '.repaired' not in p:
                    keeper = p
                    break
            if keeper is None:
                keeper = lst[0]
            for p in lst:
                if p == keeper:
                    continue
                src = Path(p)
                dest = qroot / src.name
                if dest.exists():
                    dest = dest.with_name(dest.stem + '_' + str(int(dest.stat().st_mtime)) + dest.suffix)
                try:
                    src.rename(dest)
                    moved += 1
                except Exception:
                    print(f"Failed to move {src} -> {dest}")
        print(f"Moved {moved} duplicate files to {qroot}")

    return 0

if __name__ == '__main__':
    raise SystemExit(main())
