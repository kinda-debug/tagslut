#!/usr/bin/env python3
"""Find content duplicates inside a repaired staging directory (name-independent).

Outputs a CSV with groups of files that share the same PCM SHA1. Default is read-only.

Usage:
  python3 -m scripts.dedupe_repaired --repaired /path/to/ReallyRepaired --out repaired_dupes.csv [--limit 200] [--quarantine /path/to/quarantine] [--move]

If --move is set, duplicates (all but the first in each group) are moved to the quarantine dir.
"""
from __future__ import annotations
import argparse
import csv
import os
import sys
import subprocess
from pathlib import Path

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
    p.add_argument("--out", default="repaired_dupes.csv")
    p.add_argument("--limit", type=int, default=0, help="0 = all files")
    p.add_argument("--quarantine", default=None, help="Directory to move duplicates into when --move is set")
    p.add_argument("--move", action="store_true", help="Move duplicate files (all but first) to quarantine")
    args = p.parse_args(argv)

    repaired_root = Path(args.repaired)
    out_csv = Path(args.out)
    if not repaired_root.is_dir():
        print("Repaired root not found:", repaired_root); return 2

    if compute_pcm_sha1 is None:
        print("compute_pcm_sha1 not available; run with `python -m` inside the repo or ensure import path.")
        return 3

    hashes = {}
    checked = 0
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            path = Path(root) / name
            try:
                sz = path.stat().st_size
            except Exception:
                continue
            # compute PCM SHA1
            h = compute_pcm_sha1(path)
            hashes.setdefault(h, []).append(str(path))
            checked += 1
            if args.limit and args.limit > 0 and checked >= args.limit:
                break
        if args.limit and args.limit > 0 and checked >= args.limit:
            break

    # build groups where hash is not None and multiple entries
    groups = [(h, paths) for h, paths in hashes.items() if h is not None and len(paths) > 1]
    groups.sort(key=lambda t: (-len(t[1]), t[0]))

    with out_csv.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['pcm_hash','count','paths'])
        writer.writeheader()
        for h, paths in groups:
            writer.writerow({'pcm_hash': h, 'count': len(paths), 'paths': ' | '.join(paths)})

    print(f"Checked {checked} files. Found {len(groups)} duplicate groups. Wrote {out_csv}")

    if args.move:
        if args.quarantine is None:
            print("--move requires --quarantine to be set. Aborting move.")
            return 4
        qroot = Path(args.quarantine)
        qroot.mkdir(parents=True, exist_ok=True)
        moved = 0
        for h, paths in groups:
            keeper = Path(paths[0])
            for p in paths[1:]:
                src = Path(p)
                dest = qroot / src.name
                # avoid overwriting existing quarantine files
                if dest.exists():
                    dest = dest.with_name(dest.stem + '_' + str(int(dest.stat().st_mtime)) + dest.suffix)
                src.rename(dest)
                moved += 1
        print(f"Moved {moved} duplicate files to {qroot}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
