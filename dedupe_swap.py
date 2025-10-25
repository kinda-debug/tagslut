#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deduplicate/health-verify between:
  MUSIC root: /Volumes/dotad/MUSIC
  DUPE  root: /Volumes/dotad/DD

Rules:
- Prefer MUSIC copy if healthy AND (duration >= other - tol) AND (size >= other).
- Otherwise if DD is healthier/longer/larger, swap DD into MUSIC.
- Flag items where MUSIC is corrupted and no better dupe exists.
- Dry-run by default. Use --apply to perform operations.

Matching strategy: by basename (case-insensitive). If multiple MUSIC matches
exist for the same basename, the longest MUSIC candidate is used.

Outputs:
- CSV report with per-file decisions and metrics.
- Structured backups for replaced files under --backup-root.

Author: generated for Georges (complete script, no external Python deps).
"""

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".aifc",
    ".ogg", ".opus", ".wma", ".mka", ".mkv", ".alac"
}

def which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

HAVE_FFPROBE = which("ffprobe") is not None
HAVE_FFMPEG  = which("ffmpeg")  is not None
HAVE_FLAC    = which("flac")    is not None

def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return 999, "", f"{type(e).__name__}: {e}"

def ffprobe_duration(path: Path) -> Optional[float]:
    if not HAVE_FFPROBE:
        return None
    # Fast, clean numeric output
    rc, out, err = run_cmd([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ])
    if rc != 0:
        return None
    try:
        val = float(out.strip())
        if math.isfinite(val) and val > 0:
            return val
    except:
        pass
    return None

def codec_info(path: Path) -> Optional[str]:
    if not HAVE_FFPROBE:
        return None
    rc, out, err = run_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,codec_type",
        "-of", "json",
        str(path)
    ])
    if rc != 0:
        return None
    try:
        data = json.loads(out)
        streams = data.get("streams", [])
        for s in streams:
            if s.get("codec_type") == "audio":
                return s.get("codec_name")
    except:
        return None
    return None

def decode_health_check(path: Path) -> Tuple[bool, str]:
    """
    Returns (healthy_bool, note)
    Strategy:
      - For FLAC, prefer `flac -t` if available (fast & reliable).
      - Otherwise, use `ffmpeg -v error -i <file> -f null -` to detect decode errors.
    """
    ext = path.suffix.lower()
    if ext == ".flac" and HAVE_FLAC:
        rc, out, err = run_cmd(["flac", "-t", str(path)])
        return (rc == 0, "flac -t ok" if rc == 0 else f"flac -t failed: {err[:200]}")
    if HAVE_FFMPEG:
        # -xerror: treat warnings as errors, stop on first error
        rc, out, err = run_cmd(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"])
        return (rc == 0, "ffmpeg decode ok" if rc == 0 else f"ffmpeg decode failed: {err[:200]}")
    # Fallback: no tools; assume unknown -> treat as unhealthy so it gets flagged instead of silently kept
    return (False, "no ffmpeg/flac available")

def file_metrics(path: Path) -> Dict:
    size = path.stat().st_size
    dur = ffprobe_duration(path)
    healthy, health_note = decode_health_check(path)
    codc = codec_info(path)
    return {
        "size": size,
        "duration": dur,
        "healthy": healthy,
        "health_note": health_note,
        "codec": codc
    }

def better_choice(
    music: Dict, dd: Dict, tol_sec: float
) -> Tuple[str, str]:
    """
    Decide which file to keep in MUSIC vs DD candidate.
    Returns (decision, reason)
      decision in {"KEEP_MUSIC", "SWAP_IN", "BOTH_CORRUPT", "NO_DECISION"}
    Rules:
      1) If both corrupt -> BOTH_CORRUPT.
      2) If MUSIC healthy and DD not -> KEEP_MUSIC.
      3) If DD healthy and MUSIC not -> SWAP_IN.
      4) If both healthy:
          - Prefer longer duration (>= other + tol).
          - If durations ~equal within tol: prefer larger size.
          - If tie: KEEP_MUSIC.
    """
    m_ok, d_ok = music["healthy"], dd["healthy"]
    m_dur, d_dur = music["duration"], dd["duration"]
    m_size, d_size = music["size"], dd["size"]

    if not m_ok and not d_ok:
        return "BOTH_CORRUPT", "Both failed decode-health checks"

    if m_ok and not d_ok:
        return "KEEP_MUSIC", "MUSIC healthy; DD not"

    if d_ok and not m_ok:
        return "SWAP_IN", "DD healthy; MUSIC not"

    # both healthy
    # Compare duration first (allowing for missing duration)
    if m_dur is not None and d_dur is not None:
        if d_dur > m_dur + tol_sec:
            return "SWAP_IN", f"DD longer ({d_dur:.3f}s > {m_dur:.3f}s)"
        if m_dur > d_dur + tol_sec:
            return "KEEP_MUSIC", f"MUSIC longer ({m_dur:.3f}s > {d_dur:.3f}s)"
        # durations effectively equal -> compare size
        if d_size > m_size:
            return "SWAP_IN", f"Dur≈; DD larger ({d_size} > {m_size})"
        if m_size >= d_size:
            return "KEEP_MUSIC", f"Dur≈; MUSIC larger-or-equal ({m_size} >= {d_size})"
        # fallback
        return "KEEP_MUSIC", "Dur≈; Size tie; default keep MUSIC"

    # If one duration missing, fall back to size then health (already equal)
    if m_dur is None and d_dur is not None:
        # prefer the one with known longer duration
        return "SWAP_IN", "DD has known duration; MUSIC missing duration"
    if d_dur is None and m_dur is not None:
        return "KEEP_MUSIC", "MUSIC has known duration; DD missing duration"

    # Both durations None -> compare sizes
    if d_size > m_size:
        return "SWAP_IN", f"No duration; DD larger ({d_size} > {m_size})"
    if m_size >= d_size:
        return "KEEP_MUSIC", f"No duration; MUSIC larger-or-equal ({m_size} >= {d_size})"

    return "KEEP_MUSIC", "Fallback keep MUSIC"

def safe_rename(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".swaptmp")
    if tmp.exists():
        tmp.unlink()
    shutil.move(str(src), str(tmp))
    if dst.exists():
        dst.unlink()
    shutil.move(str(tmp), str(dst))

def copy_over(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".copytmp")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(str(src), str(tmp))
    # atomic-ish replace
    if dst.exists():
        dst.unlink()
    shutil.move(str(tmp), str(dst))

def rel_under(base: Path, child: Path) -> str:
    try:
        return str(child.relative_to(base))
    except ValueError:
        return child.name

def collect_music_index(music_root: Path) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = defaultdict(list)
    for root, dirs, files in os.walk(music_root):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in AUDIO_EXTS:
                index[p.name.lower()].append(p)
    return index

def choose_music_candidate(paths: List[Path]) -> Path:
    """
    If multiple MUSIC files share the same basename, pick the 'best' candidate:
    - Longest duration among them (falls back to largest size).
    """
    if len(paths) == 1:
        return paths[0]
    best = None
    best_tuple = None  # (has_dur, dur, size)
    for p in paths:
        m = file_metrics(p)
        dur = m["duration"]
        size = m["size"]
        tup = (dur is not None, dur if dur is not None else -1.0, size)
        if (best_tuple is None) or (tup > best_tuple):
            best = p
            best_tuple = tup
    return best if best is not None else paths[0]

def main():
    ap = argparse.ArgumentParser(description="Ensure best copies in MUSIC vs DD duplicates.")
    ap.add_argument("--music-root", default="/Volumes/dotad/MUSIC", type=str)
    ap.add_argument("--dupe-root",  default="/Volumes/dotad/DD",     type=str)
    ap.add_argument("--report",     default=str(Path.cwd() / f"dedupe_report_{int(time.time())}.csv"), type=str)
    ap.add_argument("--backup-root",default="/Volumes/dotad/DD/_replacements_backup", type=str,
                    help="Where original MUSIC files get moved when swapped")
    ap.add_argument("--consumed-root", default="/Volumes/dotad/DD/_consumed_dupes", type=str,
                    help="Where DD files get moved after being copied into MUSIC")
    ap.add_argument("--tolerance-sec", default=0.5, type=float, help="Duration equality tolerance")
    ap.add_argument("--apply", action="store_true", help="Actually perform swaps/copies/moves")
    ap.add_argument("--exts", default=",".join(sorted(AUDIO_EXTS)), type=str,
                    help="Comma-separated audio extensions to include")
    args = ap.parse_args()

    music_root = Path(args.music_root).resolve()
    dupe_root  = Path(args.dupe_root).resolve()
    backup_root   = Path(args.backup_root).resolve()
    consumed_root = Path(args.consumed_root).resolve()
    tol = float(args.tolerance_sec)
    selected_exts = {e.strip().lower() if e.strip().startswith(".") else "."+e.strip().lower()
                     for e in args.exts.split(",") if e.strip()}

    if not music_root.exists():
        print(f"ERROR: MUSIC root not found: {music_root}", file=sys.stderr)
        sys.exit(2)
    if not dupe_root.exists():
        print(f"ERROR: DUPE root not found: {dupe_root}", file=sys.stderr)
        sys.exit(2)

    if not HAVE_FFPROBE or not HAVE_FFMPEG:
        print("WARNING: ffprobe/ffmpeg not fully available. Health checks/duration may be limited.", file=sys.stderr)
    if ".flac" in selected_exts and not HAVE_FLAC:
        print("NOTE: 'flac' CLI not found; will use ffmpeg-based check for FLAC.", file=sys.stderr)

    # Build MUSIC index by basename
    print("Indexing MUSIC…", file=sys.stderr)
    music_index = collect_music_index(music_root)

    rows = []
    totals = {
        "pairs": 0,
        "keep_music": 0,
        "swap_in": 0,
        "both_corrupt": 0,
        "missing_in_music": 0,
        "no_decision": 0,
        "errors": 0,
    }

    # Walk DD and match by basename
    print("Scanning DD…", file=sys.stderr)
    for root, dirs, files in os.walk(dupe_root):
        # skip our own working folders
        if Path(root).resolve().is_relative_to(backup_root) or Path(root).resolve().is_relative_to(consumed_root):
            continue
        for f in files:
            dd_path = Path(root) / f
            if dd_path.suffix.lower() not in selected_exts:
                continue

            dd_base = dd_path.name.lower()
            music_candidates = music_index.get(dd_base, [])

            if not music_candidates:
                totals["missing_in_music"] += 1
                rows.append({
                    "status": "MISSING_IN_MUSIC",
                    "reason": "No basename match found in MUSIC",
                    "music_path": "",
                    "dd_path": str(dd_path),
                    "m_duration": "",
                    "d_duration": f"",
                    "m_size": "",
                    "d_size": f"{dd_path.stat().st_size}",
                    "m_healthy": "",
                    "d_healthy": "",
                    "m_codec": "",
                    "d_codec": ""
                })
                continue

            music_path = choose_music_candidate(music_candidates)
            totals["pairs"] += 1

            try:
                m = file_metrics(music_path)
                d = file_metrics(dd_path)
            except Exception as e:
                totals["errors"] += 1
                rows.append({
                    "status": "ERROR",
                    "reason": f"metrics failed: {type(e).__name__}: {e}",
                    "music_path": str(music_path),
                    "dd_path": str(dd_path),
                    "m_duration": "",
                    "d_duration": "",
                    "m_size": "",
                    "d_size": "",
                    "m_healthy": "",
                    "d_healthy": "",
                    "m_codec": "",
                    "d_codec": ""
                })
                continue

            decision, reason = better_choice(m, d, tol)

            # Perform actions if apply
            if args.apply and decision == "SWAP_IN":
                # 1) Move original MUSIC file to backup (preserve relative path under MUSIC)
                rel = rel_under(music_root, music_path)
                backup_target = backup_root / rel
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                # Use move for original -> backup
                print(f"SWAP: Moving MUSIC -> {backup_target}", file=sys.stderr)
                backup_target.parent.mkdir(parents=True, exist_ok=True)
                safe_rename(music_path, backup_target)

                # 2) Copy DD file over to MUSIC location
                print(f"SWAP: Copying DD -> MUSIC at {music_path}", file=sys.stderr)
                copy_over(dd_path, music_path)

                # 3) Move consumed DD file out of the way to avoid duplicates sticking around
                dd_rel = rel_under(dupe_root, dd_path)
                consumed_target = consumed_root / dd_rel
                consumed_target.parent.mkdir(parents=True, exist_ok=True)
                print(f"SWAP: Moving original DD -> {consumed_target}", file=sys.stderr)
                safe_rename(dd_path, consumed_target)

            # Account & log
            if decision == "KEEP_MUSIC":
                totals["keep_music"] += 1
            elif decision == "SWAP_IN":
                totals["swap_in"] += 1
            elif decision == "BOTH_CORRUPT":
                totals["both_corrupt"] += 1
            else:
                totals["no_decision"] += 1

            rows.append({
                "status": decision,
                "reason": reason,
                "music_path": str(music_path),
                "dd_path": str(dd_path),
                "m_duration": f"{m['duration']:.3f}" if m["duration"] is not None else "",
                "d_duration": f"{d['duration']:.3f}" if d["duration"] is not None else "",
                "m_size": f"{m['size']}",
                "d_size": f"{d['size']}",
                "m_healthy": "1" if m["healthy"] else "0",
                "d_healthy": "1" if d["healthy"] else "0",
                "m_codec": m["codec"] or "",
                "d_codec": d["codec"] or "",
            })

            # For visibility in long runs
            if totals["pairs"] % 100 == 0:
                print(f"Processed pairs: {totals['pairs']}…", file=sys.stderr)

    # Write report
    report_path = Path(args.report).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "status","reason","music_path","dd_path",
            "m_duration","d_duration","m_size","d_size",
            "m_healthy","d_healthy","m_codec","d_codec"
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("\nDone.")
    print(f"Report: {report_path}")
    print("Summary:")
    for k in ["pairs","keep_music","swap_in","both_corrupt","missing_in_music","no_decision","errors"]:
        print(f"  {k}: {totals[k]}")

    # Extra: print explicit list of “corrupted with no better duplicate” (MUSIC not healthy, DD not healthy)
    problems = [r for r in rows if r["status"] == "BOTH_CORRUPT"]
    if problems:
        print("\nFiles that are corrupted with no better duplicate found (investigate elsewhere):")
        for r in problems:
            print(f"  MUSIC: {r['music_path']}")
            print(f"     DD: {r['dd_path']}")
    else:
        print("\nNo pairs where both copies failed health checks.")

if __name__ == "__main__":
    main()
