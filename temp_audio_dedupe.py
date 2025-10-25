#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temp_audio_dedupe.py

Scan a root folder (default: /Volumes/dotad/TEMP) for duplicate audio,
rank each duplicate group by "health -> duration -> bitrate", keep the
single best file per group, and (optionally) move the rest to a trash dir.

No external Python deps. Uses system tools if available:
- FLAC health: `flac -t` (preferred for .flac), else `ffmpeg -v error -f null -`
- Duration: `ffprobe` (preferred)
- Audio hash:
    * For .flac: `metaflac --show-md5sum` (fast, lossless stream MD5)
    * Fallback: decode to PCM via `ffmpeg` and hash the stream

Defaults: dry run. Pass --commit to actually move files.

Examples:
  # Dry-run report only
  ./temp_audio_dedupe.py --root "/Volumes/dotad/TEMP"

  # Actually move losing dupes to _TRASH_DUPES_YYYYmmdd_HHMMSS
  ./temp_audio_dedupe.py --root "/Volumes/dotad/TEMP" --commit

  # Faster but stricter (hash file bytes only; won't detect re-encodes)
  ./temp_audio_dedupe.py --root "/Volumes/dotad/TEMP" --hash-mode file --commit

  # Limit to FLACs, use 12 workers
  ./temp_audio_dedupe.py --exts ".flac" --workers 12 --commit
"""
import argparse
import csv
import datetime as dt
import hashlib
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional, Tuple, List

# ------------- Utilities -------------
PRINT_LOCK = threading.Lock()

def info(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)

def which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

def run(cmd: List[str], stdin=None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd, input=stdin, capture_output=True, text=True, check=False
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except Exception as e:
        return 1, "", str(e)

def human_bytes(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.2f} {units[i]}"

# ------------- External tools availability -------------
HAVE_FFPROBE = bool(which("ffprobe"))
HAVE_FFMPEG  = bool(which("ffmpeg"))
HAVE_FLAC    = bool(which("flac"))
HAVE_METAFLAC= bool(which("metaflac"))

# ------------- Inspectors -------------
def get_duration_seconds(path: Path) -> Optional[float]:
    """Return duration in seconds using ffprobe if available; None if unknown."""
    if not HAVE_FFPROBE:
        return None
    # Try stream duration first, then format duration
    for entry in ("stream=duration", "format=duration"):
        rc, out, _ = run([
            "ffprobe","-v","error",
            "-select_streams","a:0",
            "-show_entries", entry,
            "-of","default=nw=1:nk=1",
            str(path)
        ])
        if rc == 0 and out:
            try:
                val = float(out)
                if math.isfinite(val) and val > 0:
                    return val
            except ValueError:
                pass
    return None

def check_health(path: Path, ext: str) -> Tuple[bool, str]:
    """
    Return (healthy, note).
    For .flac prefer `flac -t`. Otherwise try decoding with ffmpeg to null sink.
    """
    if ext == ".flac" and HAVE_FLAC:
        rc, out, err = run(["flac","-s","-t",str(path)])
        if rc == 0:
            return True, "flac -t OK"
        else:
            note = (out or err)[:200]
            return False, f"flac -t FAIL: {note}"
    if HAVE_FFMPEG:
        rc, out, err = run(["ffmpeg","-v","error","-i",str(path),"-f","null","-","-y"])
        if rc == 0 and not err:
            return True, "ffmpeg decode OK"
        # ffmpeg may write errors to stderr
        note = (out + "\n" + err).strip()[:200]
        return False, f"ffmpeg decode FAIL: {note or 'unknown'}"
    # No tool to check
    return True, "no health tool; assumed OK"

def get_audio_hash(path: Path, ext: str, hash_mode: str) -> Tuple[str, str]:
    """
    Return (key_type, hexhash).
    key_type is one of: "AUD" (audio-level), "FILE" (file bytes).
    """
    if hash_mode == "file":
        return "FILE", sha1_file(path)

    # Try FLAC stream MD5 if available
    if ext == ".flac" and HAVE_METAFLAC:
        rc, out, err = run(["metaflac","--show-md5sum", str(path)])
        if rc == 0 and out:
            md5 = out.strip().lower()
            if md5 and md5 != "00000000000000000000000000000000":
                return "AUD", md5

    # Fallback: hash decoded PCM via ffmpeg
    if HAVE_FFMPEG:
        # Decode to 16-bit PCM, mono to stabilize across channels if needed
        cmd = ["ffmpeg","-v","error","-i",str(path),
               "-ac","2","-f","s16le","-"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            return "FILE", sha1_file(path)
        h = hashlib.sha1()
        try:
            while True:
                chunk = proc.stdout.read(1024*1024)
                if not chunk:
                    break
                h.update(chunk)
        finally:
            stdout, stderr = proc.communicate()
        # Even if decode had errors, the hash still distinguishes content
        return "AUD", h.hexdigest()

    # Last resort
    return "FILE", sha1_file(path)

def sha1_file(path: Path, bufsize: int = 2**20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

# ------------- Core -------------
AUDIO_EXTS = {".flac",".wav",".aiff",".aif",".mp3",".m4a",".aac",".ogg",".opus",".wv",".ape",".wma",".dsf"}

def scan_files(root: Path, exts: set) -> List[Path]:
    files = []
    skip_dirs = {"_TRASH_DUPES"}
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip our trash dirs if present
        if any(d.startswith("_TRASH_DUPES") for d in Path(dirpath).parts):
            continue
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                files.append(p)
    return files

def inspect_one(path: Path, hash_mode: str) -> Dict:
    ext = path.suffix.lower()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "error": "missing"}
    size = stat.st_size
    mtime = stat.st_mtime

    duration = get_duration_seconds(path)
    healthy, health_note = check_health(path, ext)
    key_type, audio_hash = get_audio_hash(path, ext, hash_mode)
    file_sha1 = sha1_file(path) if key_type != "FILE" else audio_hash

    bitrate_kbps = None
    if duration and duration > 0:
        bitrate_kbps = (size * 8.0 / duration) / 1000.0

    return {
        "path": str(path),
        "ext": ext,
        "exists": True,
        "size": size,
        "mtime": mtime,
        "duration": duration,
        "healthy": healthy,
        "health_note": health_note,
        "key_type": key_type,     # "AUD" or "FILE"
        "audio_hash": audio_hash, # hex
        "file_sha1": file_sha1,
        "bitrate_kbps": bitrate_kbps,
    }

def rank_key(item: Dict) -> Tuple:
    # Higher is better
    healthy = 1 if item.get("healthy") else 0
    duration = item.get("duration") or 0.0
    bitrate = item.get("bitrate_kbps") or 0.0
    # Prefer newer mtime slightly as a last resort tie-breaker
    mtime = item.get("mtime") or 0.0
    return (healthy, round(duration, 3), round(bitrate, 3), mtime)

def choose_winner(group_items: List[Dict]) -> int:
    """Return index of the best item to keep."""
    best_idx = 0
    best_score = rank_key(group_items[0])
    for i in range(1, len(group_items)):
        s = rank_key(group_items[i])
        if s > best_score:
            best_score = s
            best_idx = i
    return best_idx

def move_to_trash(src: Path, trash_root: Path) -> Path:
    rel = src.relative_to(src.anchor) if src.is_absolute() else src
    # Make a sane relative path inside trash: keep folder structure under root
    dest = trash_root / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stem = dest.stem
        suf  = dest.suffix
        dest = dest.with_name(f"{stem}__{sha1_file(src)[:8]}{suf}")
    shutil.move(str(src), str(dest))
    return dest

# ------------- Main -------------
def main():
    ap = argparse.ArgumentParser(description="Audio deduper for a folder (keep healthiest/longest/highest bitrate per audio-hash).")
    ap.add_argument("--root", default="/Volumes/dotad/TEMP", help="Root folder to scan")
    ap.add_argument("--exts", default=".flac,.mp3,.m4a,.wav,.aiff,.aif,.opus,.ogg,.wv,.ape",
                    help="Comma-separated list of extensions to include")
    ap.add_argument("--workers", type=int, default=8, help="Thread workers (I/O bound)")
    ap.add_argument("--hash-mode", choices=["auto","file"], default="auto",
                    help="auto: FLAC stream MD5 or PCM hash; file: hash file bytes only")
    ap.add_argument("--commit", action="store_true",
                    help="Actually move losing dupes to trash dir. Default is dry run.")
    ap.add_argument("--trash-dir", default=None,
                    help="Optional explicit trash dir; default creates _TRASH_DUPES_<timestamp> under --root")
    ap.add_argument("--report-csv", default=None,
                    help="Optional CSV path for detailed report")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        info(f"ERROR: Root not found or not a directory: {root}")
        sys.exit(2)

    exts = {e.strip().lower() if e.strip().startswith(".") else "."+e.strip().lower()
            for e in args.exts.split(",") if e.strip()}
    exts = exts & AUDIO_EXTS if exts else AUDIO_EXTS

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_dir = Path(args.trash_dir) if args.trash_dir else (root / f"_TRASH_DUPES_{ts}")
    report_csv = Path(args.report_csv) if args.report_csv else (root / f"_DEDUP_REPORT_{ts}.csv")

    info(f"Scan root: {root}")
    info(f"Extensions: {', '.join(sorted(exts))}")
    info(f"Workers: {args.workers}")
    info(f"Hash mode: {args.hash_mode}")
    info(f"Health tools: flac={HAVE_FLAC} ffmpeg={HAVE_FFMPEG} ffprobe={HAVE_FFPROBE} metaflac={HAVE_METAFLAC}")
    info("Mode: DRY RUN (no moves)" if not args.commit else f"Mode: COMMIT (trash -> {trash_dir})")
    info("Walking filesystem...")

    files = scan_files(root, exts)
    total = len(files)
    if total == 0:
        info("No candidate files found.")
        return
    info(f"Found {total} files to inspect.")

    stop_flag = False
    def handle_sigint(signum, frame):
        nonlocal stop_flag
        stop_flag = True
        info("\nInterrupted: will finish current tasks and write partial report.")
    signal.signal(signal.SIGINT, handle_sigint)

    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut2path = {ex.submit(inspect_one, p, args.hash_mode): p for p in files}
        done = 0
        for fut in as_completed(fut2path):
            if stop_flag:
                break
            res = fut.result()
            results.append(res)
            done += 1
            if done % 50 == 0:
                info(f"… inspected {done}/{total}")

    # Group by audio key
    groups: Dict[str, List[Dict]] = {}
    for r in results:
        if not r.get("exists"):
            continue
        key_type = r.get("key_type") or "FILE"
        key_val  = r.get("audio_hash") or r.get("file_sha1")
        if not key_val:
            # fallback to file sha1
            key_type = "FILE"
            key_val = r.get("file_sha1")
        if not key_val:
            # give up: unique key per file
            key = f"UNIQ:{r['path']}"
        else:
            key = f"{key_type}:{key_val}"
        groups.setdefault(key, []).append(r)

    dup_groups = {k: v for (k,v) in groups.items() if len(v) > 1}
    info(f"Total groups: {len(groups)}  | Duplicate groups: {len(dup_groups)}")

    # Prepare report
    fieldnames = [
        "group_key","keep","path","ext","size_bytes","size_human",
        "duration_sec","bitrate_kbps","healthy","health_note",
        "key_type","audio_hash","file_sha1","action","dest"
    ]
    kept = 0
    moved = 0
    plan: List[Dict] = []

    for gkey, items in dup_groups.items():
        winner_idx = choose_winner(items)
        for idx, item in enumerate(sorted(items, key=rank_key, reverse=True)):
            keep = (idx == 0)
            action = "keep" if keep else ("move" if args.commit else "would-move")
            dest = ""
            if not keep and args.commit:
                # actual move happens later to avoid partial state if interrupted
                pass
            plan.append({
                "group_key": gkey,
                "keep": keep,
                "path": item["path"],
                "ext": item["ext"],
                "size_bytes": item["size"],
                "size_human": human_bytes(item["size"]),
                "duration_sec": round(item.get("duration") or 0.0, 3),
                "bitrate_kbps": round(item.get("bitrate_kbps") or 0.0, 3),
                "healthy": item.get("healthy"),
                "health_note": item.get("health_note") or "",
                "key_type": item.get("key_type"),
                "audio_hash": item.get("audio_hash"),
                "file_sha1": item.get("file_sha1"),
                "action": action,
                "dest": dest,
            })
            if keep:
                kept += 1

    # Execute moves if commit
    if args.commit and plan:
        trash_dir.mkdir(parents=True, exist_ok=True)
        for row in plan:
            if row["action"] == "move":
                src = Path(row["path"])
                if src.exists():
                    dest = move_to_trash(src, trash_dir)
                    row["dest"] = str(dest)
                    moved += 1

    # Write report
    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in plan:
            w.writerow(row)

    # Summary
    total_groups = len(groups)
    total_dupe_groups = len(dup_groups)
    total_files = len(results)
    info("\n--- Summary ---")
    info(f"Files inspected: {total_files}")
    info(f"Duplicate groups: {total_dupe_groups}")
    info(f"Kept (winners): {kept}")
    if args.commit:
        info(f"Moved (losers): {moved} -> {trash_dir}")
    else:
        would_move = sum(1 for r in plan if r["action"] == "would-move")
        info(f"Losers (dry-run): {would_move} (use --commit to move)")
    info(f"Report: {report_csv}")

if __name__ == "__main__":
    main()
