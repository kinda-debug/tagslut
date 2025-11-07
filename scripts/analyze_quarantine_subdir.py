#!/usr/bin/env python3
"""Analyze a Quarantine subdirectory for duplicates, stitched files and length issues.

Produces a CSV with one row per file containing: path,size,reported_duration,
decoded_duration,sample_rate,channels,pcm_sha1,window_fingerprint_count,stitched_flag,truncated_flag

This script is safe/read-only by default. It uses ffprobe/ffmpeg and optionally
fpcalc (Chromaprint) if available. It is intended as a resumable, batched
analyzer for large directories.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


def which(cmd: str) -> Optional[str]:
    from shutil import which as _which

    return _which(cmd)


def ffprobe_info(path: str) -> dict:
    if which("ffprobe") is None:
        raise FileNotFoundError("ffprobe not found in PATH")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=channels,sample_rate,nb_read_frames",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    out = p.stdout.strip().splitlines()
    info = {"duration": None, "sample_rate": None, "channels": None, "nb_read_frames": None}
    if out:
        # ffprobe returns lines in the order requested; robustly try to parse
        try:
            # duration may be first
            dur = float(out[0])
            info["duration"] = dur
        except Exception:
            pass
        # scan for numeric tokens in output lines for sample_rate, channels, frames
        for line in out:
            try:
                n = float(line)
            except Exception:
                continue
            # heuristics
            if n > 1e4 and info.get("sample_rate") is None:
                info["sample_rate"] = int(n)
            elif n in (1.0, 2.0, 4.0, 6.0, 8.0) and info.get("channels") is None:
                info["channels"] = int(n)
            elif n >= 1 and info.get("nb_read_frames") is None:
                # plausibly frame count
                info["nb_read_frames"] = int(n)
    return info


def compute_pcm_sha1(path: str) -> Optional[str]:
    """Compute PCM SHA1 by decoding to WAV on stdout and hashing the raw bytes.
    Returns hex digest or None on error.
    """
    ffmpeg = which("ffmpeg")
    if not ffmpeg:
        return None
    cmd = [ffmpeg, "-v", "error", "-i", path, "-f", "wav", "-"]
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        h = hashlib.sha1()
        assert p.stdout is not None
        while True:
            chunk = p.stdout.read(65536)
            if not chunk:
                break
            h.update(chunk)
        p.wait()
        if p.returncode != 0:
            return None
        return h.hexdigest()
    except Exception:
        return None


def windowed_fpcalc_count(path: str, window: int = 30, step: Optional[int] = None) -> int:
    """Compute fpcalc fingerprints across sliding windows and return number of distinct fingerprints.
    If fpcalc not available, return 0.
    """
    if which("fpcalc") is None or which("ffmpeg") is None:
        return 0
    step = step or (window - 10 if window > 10 else window)
    # compute file duration first
    info = ffprobe_info(path)
    dur = info.get("duration") or 0
    if dur <= 0:
        return 0
    fingerprints = set()
    off = 0.0
    while off < dur:
        # extract window to a temp wav and fingerprint
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpf:
            tmpfn = tmpf.name
        try:
            cmd = [
                which("ffmpeg"),
                "-v",
                "error",
                "-ss",
                str(off),
                "-t",
                str(window),
                "-i",
                path,
                "-f",
                "wav",
                tmpfn,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # run fpcalc on tmpfn
            p = subprocess.run([which("fpcalc"), tmpfn], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            out = p.stdout
            for line in out.splitlines():
                if line.startswith("FINGERPRINT="):
                    fingerprints.add(line.split("=", 1)[1].strip())
                    break
        finally:
            try:
                os.remove(tmpfn)
            except Exception:
                pass
        off += step
    return len(fingerprints)


def detect_length_mismatch(path: str) -> tuple[Optional[float], Optional[float]]:
    info = ffprobe_info(path)
    reported = info.get("duration")
    decoded = None
    sr = info.get("sample_rate")
    frames = info.get("nb_read_frames")
    if frames and sr:
        try:
            decoded = frames / float(sr)
        except Exception:
            decoded = None
    return reported, decoded


def analyze_one(path: str) -> dict:
    st = os.stat(path)
    size = st.st_size
    info = ffprobe_info(path)
    reported = info.get("duration")
    sample_rate = info.get("sample_rate")
    channels = info.get("channels")
    frames = info.get("nb_read_frames")
    decoded = None
    if frames and sample_rate:
        decoded = frames / float(sample_rate)
    pcm = compute_pcm_sha1(path)
    fpcount = windowed_fpcalc_count(path)
    stitched = fpcount > 1
    truncated = False
    # if decoded exists and reported exists and decoded > reported * 1.01
    if decoded and reported and decoded > reported * 1.02:
        truncated = True
    return {
        "path": path,
        "size": size,
        "reported_duration": reported,
        "decoded_duration": decoded,
        "sample_rate": sample_rate,
        "channels": channels,
        "pcm_sha1": pcm,
        "window_fp_count": fpcount,
        "stitched": stitched,
        "truncated": truncated,
    }


def main():
    ap = argparse.ArgumentParser(description="Analyze a Quarantine subdir for audio issues and fingerprints")
    ap.add_argument("--dir", required=True, help="Quarantine subdir to analyze")
    ap.add_argument("--out", default="out/quarantine_analysis.csv", help="CSV output path")
    ap.add_argument("--workers", type=int, default=2, help="Parallel workers")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of files (0 = all)")
    args = ap.parse_args()

    d = Path(args.dir)
    if not d.is_dir():
        print("Not a directory: %s" % d)
        sys.exit(2)

    files = [str(p) for p in d.rglob("*.flac")]
    files.sort()
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=[
            "path",
            "size",
            "reported_duration",
            "decoded_duration",
            "sample_rate",
            "channels",
            "pcm_sha1",
            "window_fp_count",
            "stitched",
            "truncated",
        ])
        writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(analyze_one, p): p for p in files}
            for fut in as_completed(futures):
                try:
                    row = fut.result()
                except Exception as e:
                    row = {"path": futures[fut], "error": str(e)}
                writer.writerow(row)
                csvf.flush()


if __name__ == "__main__":
    main()
