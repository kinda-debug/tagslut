#!/usr/bin/env python3
"""Compare repaired staging against the MUSIC library and recommend actions.

Usage: python3 scripts/reconcile_repaired.py --repaired /Volumes/dotad/ReallyRepaired \
    --music /Volumes/dotad/MUSIC --out report.csv [--limit 200] [--hash-on-diff]

The script is conservative: it produces a CSV with one row per repaired file and a
recommendation. No files are moved or deleted unless --apply is specified.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path
import os
import sys
from typing import Optional

# reuse compute_pcm_sha1 from the repo helpers when available
try:
    from scripts.lib.common import compute_pcm_sha1
except Exception:
    compute_pcm_sha1 = None  # type: ignore


def ffprobe_duration(path: Path) -> Optional[float]:
    try:
        out = subprocess.check_output([
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ], stderr=subprocess.DEVNULL)
        return float(out.decode().strip())
    except Exception:
        return None


def human_bytes(n: int) -> str:
    for unit in ["B", "KiB", "MiB", "GiB"]:
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TiB"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--repaired", required=True)
    p.add_argument("--music", required=True)
    p.add_argument("--out", default="reconcile_report.csv")
    p.add_argument("--limit", type=int, default=200, help="Limit files scanned (0 = all)")
    p.add_argument("--hash-on-diff", action="store_true", help="Compute PCM SHA1 when size/duration differ")
    p.add_argument("--apply", action="store_true", help="Apply recommended actions (DANGEROUS)")
    args = p.parse_args(argv)

    repaired_root = Path(args.repaired)
    music_root = Path(args.music)
    out_csv = Path(args.out)

    if not repaired_root.is_dir():
        print("Repaired root not found:", repaired_root)
        return 2
    if not music_root.is_dir():
        print("Music root not found:", music_root)
        return 2

    rows = []
    count = 0
    for root, dirs, files in os.walk(repaired_root):
        for name in files:
            if not name.lower().endswith(".flac"):
                continue
            rep_path = Path(root) / name
            rel = rep_path.relative_to(repaired_root)
            music_path = music_root.joinpath(rel)

            rep_size = rep_path.stat().st_size if rep_path.exists() else None
            music_exists = music_path.exists()
            music_size = music_path.stat().st_size if music_exists else None

            rep_dur = ffprobe_duration(rep_path)
            music_dur = ffprobe_duration(music_path) if music_exists else None

            pcm_same = "NA"
            if args.hash_on_diff and compute_pcm_sha1 is not None and music_exists:
                try:
                    rep_hash = compute_pcm_sha1(rep_path)
                    music_hash = compute_pcm_sha1(music_path)
                    pcm_same = "YES" if (rep_hash and music_hash and rep_hash == music_hash) else "NO"
                except Exception:
                    pcm_same = "ERR"

            # decision rules
            if not music_exists:
                action = "COPY->MUSIC"
            else:
                # identical by size & duration (within small tolerance)
                tol = 0.5
                sizes_equal = rep_size == music_size
                durs_equal = (rep_dur is not None and music_dur is not None and abs(rep_dur - music_dur) <= tol)
                if sizes_equal and (durs_equal or rep_dur is None or music_dur is None):
                    action = "KEEP_MUSIC (duplicate)"
                else:
                    # prefer higher size and longer duration heuristically
                    if rep_dur and music_dur:
                        if abs(rep_dur - music_dur) < tol:
                            # durations close but sizes differ
                            action = "REPLACE_IF_REPAIRED_LARGER" if rep_size and music_size and rep_size > music_size else "KEEP_MUSIC"
                        else:
                            # longer duration preferred
                            action = "REPLACE_MUSIC_WITH_REPAIRED" if rep_dur > music_dur else "KEEP_MUSIC"
                    else:
                        # fall back to size
                        if rep_size and music_size:
                            action = "REPLACE_IF_REPAIRED_LARGER" if rep_size > music_size else "KEEP_MUSIC"
                        else:
                            action = "MANUAL_REVIEW"

            rows.append({
                "repaired": str(rep_path),
                "relative": str(rel),
                "music_exists": str(music_exists),
                "repaired_size": rep_size,
                "music_size": music_size,
                "repaired_dur": rep_dur,
                "music_dur": music_dur,
                "pcm_same": pcm_same,
                "recommendation": action,
            })

            count += 1
            if args.limit and args.limit > 0 and count >= args.limit:
                break
        if args.limit and args.limit > 0 and count >= args.limit:
            break

    # write CSV
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["repaired"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Wrote report: {out_csv} ({len(rows)} rows)")
    print("Summary:")
    from collections import Counter

    c = Counter(r["recommendation"] for r in rows)
    for k, v in c.items():
        print(f"  {k}: {v}")

    if args.apply:
        print("--apply passed: applying recommended actions (this may overwrite files).")
        for r in rows:
            action = r["recommendation"]
            rep = Path(r["repaired"])
            music = music_root.joinpath(r["relative"])
            if action == "COPY->MUSIC":
                music.parent.mkdir(parents=True, exist_ok=True)
                print(f"Copying {rep} -> {music}")
                subprocess.check_call(["rsync", "-a", str(rep) + "/", str(music.parent) + "/"])  # copy into parent
            elif action == "REPLACE_MUSIC_WITH_REPAIRED" or action == "REPLACE_IF_REPAIRED_LARGER":
                # backup existing
                if music.exists():
                    bak = music.with_suffix(music.suffix + ".bak")
                    print(f"Backing up {music} -> {bak}")
                    subprocess.check_call(["cp", "-p", str(music), str(bak)])
                music.parent.mkdir(parents=True, exist_ok=True)
                print(f"Replacing {music} with {rep}")
                subprocess.check_call(["cp", "-p", str(rep), str(music)])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
