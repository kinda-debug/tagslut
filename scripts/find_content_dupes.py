#!/usr/bin/env python3
"""Find content duplicates between a repaired staging and the MUSIC library.

Strategy:
- Build an index of MUSIC files keyed by file size to quickly find candidates.
- For each repaired .flac file, find MUSIC candidates with the same size and compute PCM SHA1
  for repaired + each candidate and compare.
- Write matches to `content_duplicates.csv`.

This script uses `compute_pcm_sha1` from `scripts.lib.common` if available.
"""
from __future__ import annotations
import os
import sys
import csv
import argparse
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
    p.add_argument("--music", required=True)
    p.add_argument("--out", default="content_duplicates.csv")
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    args = p.parse_args(argv)

    repaired_root = Path(args.repaired)
    music_root = Path(args.music)
    out_csv = Path(args.out)

    if not repaired_root.is_dir():
        print("Repaired root not found:", repaired_root); return 2
    if not music_root.is_dir():
        print("Music root not found:", music_root); return 2

    if compute_pcm_sha1 is None:
        print("compute_pcm_sha1 not available from scripts.lib.common; aborting.")
        return 3

    # Build size index for music files
    size_index = {}
    print("Indexing MUSIC files (this may take a while)...")
    mcount = 0
    for root, dirs, files in os.walk(music_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            path = Path(root) / name
            try:
                sz = path.stat().st_size
            except Exception:
                continue
            size_index.setdefault(sz, []).append(path)
            mcount += 1
    print(f"Indexed {mcount} MUSIC files into {len(size_index)} size buckets")

    rows = []
    checked = 0
    matched = 0
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith('.flac'):
                continue
            rep = Path(root) / name
            try:
                rsz = rep.stat().st_size
            except Exception:
                continue
            candidates = size_index.get(rsz, [])
            rep_dur = ffprobe_duration(rep)
            rep_hash = None
            if candidates:
                # compute repaired hash once
                try:
                    rep_hash = compute_pcm_sha1(rep)
                except Exception as e:
                    rep_hash = None
                for cand in candidates:
                    # compute candidate hash and compare
                    try:
                        cand_hash = compute_pcm_sha1(cand)
                    except Exception:
                        cand_hash = None
                    cand_dur = ffprobe_duration(cand)
                    is_same = (rep_hash is not None and cand_hash is not None and rep_hash == cand_hash)
                    if is_same:
                        rows.append({
                            'repaired': str(rep),
                            'music': str(cand),
                            'repaired_size': rsz,
                            'music_size': rsz,
                            'repaired_dur': rep_dur,
                            'music_dur': cand_dur,
                            'pcm_hash': rep_hash,
                            'match': 'YES',
                        })
                        matched += 1
                        # stop after first match for this repaired file
                        break
            else:
                rows.append({
                    'repaired': str(rep),
                    'music': '',
                    'repaired_size': rsz,
                    'music_size': '',
                    'repaired_dur': rep_dur,
                    'music_dur': '',
                    'pcm_hash': rep_hash,
                    'match': 'NO_CANDIDATES_BY_SIZE',
                })
            checked += 1
            if args.limit and args.limit > 0 and checked >= args.limit:
                break
        if args.limit and args.limit > 0 and checked >= args.limit:
            break

    # write CSV
    with out_csv.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['repaired','music','repaired_size','music_size','repaired_dur','music_dur','pcm_hash','match'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Checked {checked} repaired files; matched {matched} content-duplicates. Wrote {out_csv}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
