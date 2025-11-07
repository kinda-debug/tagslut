#!/usr/bin/env python3
"""Detect files whose decoded playback length differs from container-reported.

Usage: detect_playback_length_issues.py --dir /path/to/dir --out out.csv

For each FLAC found, writes: path,reported_duration,decoded_duration,ratio
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def which(cmd: str):
    from shutil import which as _which

    return _which(cmd)


def ffprobe_duration(path: str):
    cmd = [which("ffprobe"), "-v", "error",
           "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1",
           path]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True)
    out = p.stdout.strip()
    try:
        return float(out)
    except Exception:
        return None


def decoded_duration_via_frames(path: str):
    # try to get nb_read_frames and sample_rate from ffprobe
    cmd = [which("ffprobe"), "-v", "error",
           "-select_streams", "a:0",
           "-show_entries", "stream=nb_read_frames,sample_rate",
           "-of", "default=noprint_wrappers=1:nokey=1",
           path]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True)
    lines = [l.strip() for l in p.stdout.splitlines() if l.strip()]
    if len(lines) >= 2:
        try:
            frames = int(lines[0])
            sr = int(lines[1])
            return frames / float(sr)
        except Exception:
            pass
    # fallback: decode to wav and inspect frames
    if which("ffmpeg") is None:
        return None
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmpfn = tmp.name
    try:
        # limit decoding time to avoid hanging on malformed files
        try:
            subprocess.run([
                which("ffmpeg"), "-nostdin", "-hide_banner", "-v", "error",
                "-i", path, "-f", "wav", tmpfn
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except subprocess.TimeoutExpired:
            return None
        # read wave header via wave module
        import wave

        with wave.open(tmpfn, "rb") as w:
            frames = w.getnframes()
            sr = w.getframerate()
            return frames / float(sr)
    except Exception:
        return None
    finally:
        try:
            os.remove(tmpfn)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", default="out/length_issues.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.is_dir():
        print("Not a directory", file=sys.stderr)
        sys.exit(2)

    files = list(d.rglob("*.flac"))
    files.sort()
    if args.limit:
        files = files[: args.limit]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "reported", "decoded", "ratio"])
        w.writeheader()
        for p in files:
            pstr = str(p)
            reported = ffprobe_duration(pstr)
            decoded = decoded_duration_via_frames(pstr)
            ratio = None
            try:
                if reported and decoded:
                    ratio = decoded / reported
            except Exception:
                ratio = None
            w.writerow({"path": pstr, "reported": reported, "decoded": decoded,
                        "ratio": ratio})


if __name__ == "__main__":
    main()
