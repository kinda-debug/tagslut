#!/usr/bin/env python3
"""Simple read-only scan of Quarantine directory metadata.
No fingerprinting, no PCM hash, just ffprobe metadata.
Single-threaded to avoid threading/timeout issues.
"""
import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path


def which(cmd: str):
    from shutil import which as _which
    return _which(cmd)


def ffprobe_duration(path: str) -> float | None:
    """Get container-reported duration only."""
    cmd = [which("ffprobe"), "-nostdin", "-v", "error",
           "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", path]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True,
                          timeout=2)
        return float(p.stdout.strip()) if p.stdout.strip() else None
    except (subprocess.TimeoutExpired, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(
        description="Simple scan of Quarantine directory (no fingerprinting)")
    ap.add_argument("--dir", required=True, help="Directory to scan")
    ap.add_argument("--out", default="quarantine_simple.csv",
                   help="CSV output path")
    ap.add_argument("--limit", type=int, default=0,
                   help="Limit files (0=all)")
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.is_dir():
        print(f"Not a directory: {d}")
        sys.exit(2)

    files = sorted([str(p) for p in d.rglob("*.flac")])
    if args.limit and args.limit > 0:
        files = files[:args.limit]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    with open(args.out, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=[
            "path", "size", "duration"
        ])
        writer.writeheader()

        for i, path in enumerate(files, 1):
            try:
                size = os.path.getsize(path)
                duration = ffprobe_duration(path)
                row = {"path": path, "size": size, "duration": duration}
                writer.writerow(row)
                csvf.flush()
                print(f"{i:3d}/{len(files)} {os.path.basename(path)[:60]}")
            except Exception as e:
                print(f"{i:3d}/{len(files)} ERROR: {e}")

    print(f"\nDone. Output: {args.out}")


if __name__ == "__main__":
    main()
