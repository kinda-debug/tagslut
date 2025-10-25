#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DD ↔ MUSIC dedupe/health with AUDIO HASH matching.

What it does
------------
1) Index /Volumes/dotad/MUSIC (default) into an AUDIO-MD5 map (decoded stream).
   - Uses a persistent JSON cache to avoid rehashing unchanged files.
   - Excludes quarantine/working folders by default from *keeper* selection.
2) Walk /Volumes/dotad/DD, compute AUDIO-MD5 per file, and look up the match in MUSIC.
3) For each matched pair:
     - Run health check (flac -t when possible, else ffmpeg decode).
     - Compare duration (± tolerance) then size.
     - Keep MUSIC if it’s healthy and not worse; otherwise swap DD into MUSIC.
4) Flag cases where both are corrupt (no good copy).
5) Write a CSV report.

Default: dry-run. Use --apply to perform swaps.
Requires: ffmpeg (and optional flac CLI).

Author: complete standalone script for Georges.
"""

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- Config ----------

AUDIO_EXTS = {
    ".flac", ".mp3", ".m4a", ".aac", ".wav", ".aif", ".aiff", ".aifc",
    ".ogg", ".opus", ".wma", ".mka", ".mkv", ".alac"
}

EXCLUDE_DIR_NAMES_DEFAULT = {
    "_quarantine_from_gemini",
    "_replacements_backup",
    "_consumed_dupes",
    ".DS_Store",
    "@eaDir"
}

CACHE_PATH_DEFAULT = Path.home() / ".cache" / "dedupe_swap_audiohash.json"

# ---------- Utilities ----------

def which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 999, "", f"{type(e).__name__}: {e}"

HAVE_FFPROBE = which("ffprobe") is not None
HAVE_FFMPEG  = which("ffmpeg")  is not None
HAVE_FLAC    = which("flac")    is not None

HEX32_RE = re.compile(r"[0-9a-fA-F]{32}")

def audio_md5(path: Path) -> Optional[str]:
    """
    Compute decoded-audio MD5 using ffmpeg md5 muxer.
    Returns 32-hex string or None.
    """
    if not HAVE_FFMPEG:
        return None
    # We only hash the audio streams: -map 0:a
    rc, out, err = run_cmd(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-f", "md5", "-"])
    if rc != 0:
        return None
    # ffmpeg prints either "MD5=..." or bare hash depending on build; extract last 32-hex.
    m = HEX32_RE.findall(out)
    if m:
        return m[-1].lower()
    m = HEX32_RE.findall(err)
    if m:
        return m[-1].lower()
    return None

def ffprobe_duration(path: Path) -> Optional[float]:
    if not HAVE_FFPROBE:
        return None
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
        for s in data.get("streams", []):
            if s.get("codec_type") == "audio":
                return s.get("codec_name")
    except:
        pass
    return None

def decode_health_check(path: Path) -> Tuple[bool, str]:
    """
    Returns (healthy_bool, note)
    - For FLAC use 'flac -t' when available; else ffmpeg decode to null with -xerror.
    """
    ext = path.suffix.lower()
    if ext == ".flac" and HAVE_FLAC:
        rc, out, err = run_cmd(["flac", "-t", str(path)])
        return (rc == 0, "flac -t ok" if rc == 0 else f"flac -t failed")
    if HAVE_FFMPEG:
        rc, out, err = run_cmd(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"])
        return (rc == 0, "ffmpeg decode ok" if rc == 0 else "ffmpeg decode failed")
    return (False, "no ffmpeg/flac")

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

def better_choice(music: Dict, dd: Dict, tol_sec: float) -> Tuple[str, str]:
    """
    Returns (decision, reason) where decision in:
      KEEP_MUSIC | SWAP_IN | BOTH_CORRUPT | NO_DECISION
    """
    m_ok, d_ok = music["healthy"], dd["healthy"]
    m_dur, d_dur = music["duration"], dd["duration"]
    m_size, d_size = music["size"], dd["size"]

    if not m_ok and not d_ok:
        return "BOTH_CORRUPT", "Both failed health checks"
    if m_ok and not d_ok:
        return "KEEP_MUSIC", "MUSIC healthy; DD not"
    if d_ok and not m_ok:
        return "SWAP_IN", "DD healthy; MUSIC not"

    # Both healthy: prefer longer (with tolerance), then larger
    if m_dur is not None and d_dur is not None:
        if d_dur > m_dur + tol_sec:
            return "SWAP_IN", f"DD longer ({d_dur:.3f}s > {m_dur:.3f}s)"
        if m_dur > d_dur + tol_sec:
            return "KEEP_MUSIC", f"MUSIC longer ({m_dur:.3f}s > {d_dur:.3f}s)"
        if d_size > m_size:
            return "SWAP_IN", f"Dur≈; DD larger ({d_size} > {m_size})"
        return "KEEP_MUSIC", f"Dur≈; MUSIC larger-or-equal ({m_size} >= {d_size})"

    # Missing durations: fall back to size
    if d_size > m_size:
        return "SWAP_IN", f"No/partial duration; DD larger ({d_size} > {m_size})"
    return "KEEP_MUSIC", f"No/partial duration; MUSIC larger-or-equal ({m_size} >= {d_size})"

def under_dir(p: Path, ancestor: Path) -> bool:
    try:
        p.resolve().relative_to(ancestor.resolve())
        return True
    except Exception:
        return False

def ensure_dir(d: Path):
    d.mkdir(parents=True, exist_ok=True)

def safe_move(src: Path, dst: Path):
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".swaptmp")
    if tmp.exists():
        tmp.unlink()
    shutil.move(str(src), str(tmp))
    if dst.exists():
        dst.unlink()
    shutil.move(str(tmp), str(dst))

def copy_over(src: Path, dst: Path):
    ensure_dir(dst.parent)
    tmp = dst.with_suffix(dst.suffix + ".copytmp")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(str(src), str(tmp))
    if dst.exists():
        dst.unlink()
    shutil.move(str(tmp), str(dst))

# ---------- Hash cache ----------

def load_cache(cache_path: Path) -> Dict[str, Dict]:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_cache(cache_path: Path, data: Dict[str, Dict]):
    ensure_dir(cache_path.parent)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def cache_key_for(path: Path) -> str:
    st = path.stat()
    return f"{int(st.st_mtime_ns)}:{st.st_size}"

def get_hash_with_cache(path: Path, cache: Dict[str, Dict]) -> Optional[str]:
    p = str(path)
    ck = cache_key_for(path)
    ent = cache.get(p)
    if ent and ent.get("k") == ck and ent.get("h"):
        return ent["h"]
    h = audio_md5(path)
    cache[p] = {"k": ck, "h": h}
    return h

# ---------- Indexing ----------

def should_skip(path: Path, exclude_names: set) -> bool:
    # Skip if any path segment is in exclude list (simple, fast)
    for part in path.parts:
        if part in exclude_names:
            return True
    return False

def collect_music_by_hash(
    music_root: Path,
    cache: Dict[str, Dict],
    exclude_names: set,
    exts: set,
    workers: int
) -> Tuple[Dict[str, List[Path]], Dict[str, str]]:
    """
    Returns (hash -> [paths], errors) and per-file hash map (path->hash).
    """
    files: List[Path] = []
    for root, dirs, fs in os.walk(music_root):
        # prune excluded dirs
        dirs[:] = [d for d in dirs if d not in exclude_names]
        for f in fs:
            p = Path(root) / f
            if p.suffix.lower() in exts:
                files.append(p)

    path_to_hash: Dict[str, str] = {}
    h2paths: Dict[str, List[Path]] = defaultdict(list)

    def worker(p: Path):
        h = get_hash_with_cache(p, cache)
        return (p, h)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = {ex.submit(worker, p): p for p in files}
        done = 0
        for ft in as_completed(futs):
            done += 1
            if done % 200 == 0:
                print(f"[hash] MUSIC {done}/{len(files)}", file=sys.stderr)
            p, h = ft.result()
            if h:
                path_to_hash[str(p)] = h
                h2paths[h].append(p)
    return h2paths, path_to_hash

def best_music_path_for_hash(paths: List[Path]) -> Path:
    """
    If multiple MUSIC files share the same audio hash, choose the best keeper:
      - Prefer the one outside quarantine-like folders.
      - Then prefer longer duration; tie-breaker: larger size; then shortest path.
    """
    best = None
    best_key = None
    for p in paths:
        m = file_metrics(p)
        in_quar = "_quarantine_from_gemini" in p.parts
        key = (
            0 if not in_quar else 1,                 # prefer non-quarantine
            -(m["duration"] or -1.0),                # longer first (note minus)
            -m["size"],                              # larger first
            len(str(p))                              # shorter path
        )
        if best_key is None or key < best_key:
            best_key = key
            best = p
    return best or paths[0]

# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser(description="Ensure best copies in MUSIC vs DD using AUDIO HASH matching.")
    ap.add_argument("--music-root", default="/Volumes/dotad/MUSIC", type=str)
    ap.add_argument("--dupe-root",  default="/Volumes/dotad/DD",     type=str)
    ap.add_argument("--report",     default=str(Path.cwd() / f"dedupe_report_{int(time.time())}.csv"), type=str)
    ap.add_argument("--backup-root",   default="/Volumes/dotad/DD/_replacements_backup", type=str)
    ap.add_argument("--consumed-root", default="/Volumes/dotad/DD/_consumed_dupes", type=str)
    ap.add_argument("--tolerance-sec", default=0.5, type=float)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--workers", default=os.cpu_count() or 4, type=int, help="Threads for hashing")
    ap.add_argument("--exts", default=",".join(sorted(AUDIO_EXTS)), type=str)
    ap.add_argument("--cache", default=str(CACHE_PATH_DEFAULT), type=str, help="Audio hash cache JSON path")
    ap.add_argument("--include-quarantine", action="store_true",
                    help="If set, quarantine folders are allowed as keepers")
    ap.add_argument("--extra-exclude", default="", type=str,
                    help="Comma-separated extra dir names to ignore (e.g. '@eaDir,.Spotlight-V100')")
    args = ap.parse_args()

    music_root = Path(args.music_root).resolve()
    dupe_root  = Path(args.dupe_root).resolve()
    backup_root   = Path(args.backup_root).resolve()
    consumed_root = Path(args.consumed_root).resolve()
    tol = float(args.tolerance_sec)
    exts = {("." + e.strip().lower() if not e.strip().startswith(".") else e.strip().lower())
            for e in args.exts.split(",") if e.strip()}

    if not music_root.exists():
        print(f"ERROR: MUSIC root not found: {music_root}", file=sys.stderr)
        sys.exit(2)
    if not dupe_root.exists():
        print(f"ERROR: DUPE root not found: {dupe_root}", file=sys.stderr)
        sys.exit(2)
    if not HAVE_FFMPEG:
        print("ERROR: ffmpeg not found; install via Homebrew: brew install ffmpeg", file=sys.stderr)
        sys.exit(2)

    exclude_names = set(EXCLUDE_DIR_NAMES_DEFAULT)
    if args.include_quarantine and "_quarantine_from_gemini" in exclude_names:
        exclude_names.remove("_quarantine_from_gemini")
    if args.extra_exclude:
        exclude_names |= {x.strip() for x in args.extra_exclude.split(",") if x.strip()}

    # Load cache
    cache_path = Path(args.cache)
    cache = load_cache(cache_path)

    # Index MUSIC by AUDIO HASH
    print("Hash-indexing MUSIC…", file=sys.stderr)
    h2paths, path2hash = collect_music_by_hash(music_root, cache, exclude_names, exts, args.workers)

    # Prepare CSV
    rows = []
    totals = {
        "pairs": 0,
        "keep_music": 0,
        "swap_in": 0,
        "both_corrupt": 0,
        "missing_in_music": 0,
        "no_decision": 0,
        "errors": 0,
        "dupe_files": 0,
    }

    # Walk DD and match by AUDIO HASH
    print("Scanning DD…", file=sys.stderr)
    dd_files: List[Path] = []
    for root, dirs, files in os.walk(dupe_root):
        # don't skip anything under DD by default
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in exts:
                dd_files.append(p)

    # Hash DD in parallel
    def dd_worker(p: Path):
        h = get_hash_with_cache(p, cache)
        return (p, h)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(dd_worker, p): p for p in dd_files}
        done = 0
        for ft in as_completed(futs):
            done += 1
            if done % 200 == 0:
                print(f"[hash] DD {done}/{len(dd_files)}", file=sys.stderr)
            dd_path, dd_hash = ft.result()
            if not dd_hash:
                totals["errors"] += 1
                rows.append({
                    "status": "ERROR", "reason": "audio hash failed",
                    "music_path": "", "dd_path": str(dd_path),
                    "match_type": "audiohash", "in_quarantine": "",
                    "m_duration": "", "d_duration": "",
                    "m_size": "", "d_size": "",
                    "m_healthy": "", "d_healthy": "",
                    "m_codec": "", "d_codec": ""
                })
                continue

            # Match in MUSIC
            music_candidates = h2paths.get(dd_hash, [])
            if not music_candidates:
                totals["missing_in_music"] += 1
                rows.append({
                    "status": "MISSING_IN_MUSIC",
                    "reason": "no audiohash match in MUSIC",
                    "music_path": "",
                    "dd_path": str(dd_path),
                    "match_type": "audiohash",
                    "in_quarantine": "",
                    "m_duration": "", "d_duration": "",
                    "m_size": "", "d_size": f"{dd_path.stat().st_size}",
                    "m_healthy": "", "d_healthy": "",
                    "m_codec": "", "d_codec": ""
                })
                continue

            totals["dupe_files"] += 1
            music_path = best_music_path_for_hash(music_candidates)
            in_quarantine = "_quarantine_from_gemini" in music_path.parts

            try:
                m = file_metrics(music_path)
                d = file_metrics(dd_path)
            except Exception as e:
                totals["errors"] += 1
                rows.append({
                    "status": "ERROR", "reason": f"metrics failed: {type(e).__name__}: {e}",
                    "music_path": str(music_path), "dd_path": str(dd_path),
                    "match_type": "audiohash",
                    "in_quarantine": "1" if in_quarantine else "0",
                    "m_duration": "", "d_duration": "",
                    "m_size": "", "d_size": "",
                    "m_healthy": "", "d_healthy": "",
                    "m_codec": "", "d_codec": ""
                })
                continue

            totals["pairs"] += 1
            decision, reason = better_choice(m, d, tol)

            # Apply swap if needed
            if args.apply and decision == "SWAP_IN":
                # Move original MUSIC file to backup (preserving rel path)
                rel = music_path.resolve().relative_to(music_root.resolve())
                backup_target = backup_root / rel
                print(f"SWAP: MUSIC -> {backup_target}", file=sys.stderr)
                ensure_dir(backup_target.parent)
                safe_move(music_path, backup_target)

                # Copy DD into MUSIC path
                print(f"SWAP: DD -> MUSIC at {music_path}", file=sys.stderr)
                copy_over(dd_path, music_path)

                # Move consumed DD to consumed_root to avoid re-processing
                dd_rel = dd_path.resolve().relative_to(dupe_root.resolve())
                consumed_target = consumed_root / dd_rel
                print(f"SWAP: DD original -> {consumed_target}", file=sys.stderr)
                ensure_dir(consumed_target.parent)
                safe_move(dd_path, consumed_target)

            if decision == "KEEP_MUSIC":
                totals["keep_music"] += 1
            elif decision == "SWAP_IN":
                totals["swap_in"] += 1
            elif decision == "BOTH_CORRUPT":
                totals["both_corrupt"] += 1
            else:
                totals["no_decision"] += 1

            rows.append({
                "status": decision, "reason": reason,
                "music_path": str(music_path),
                "dd_path": str(dd_path),
                "match_type": "audiohash",
                "in_quarantine": "1" if in_quarantine else "0",
                "m_duration": f"{m['duration']:.3f}" if m["duration"] is not None else "",
                "d_duration": f"{d['duration']:.3f}" if d["duration"] is not None else "",
                "m_size": f"{m['size']}", "d_size": f"{d['size']}",
                "m_healthy": "1" if m["healthy"] else "0",
                "d_healthy": "1" if d["healthy"] else "0",
                "m_codec": m["codec"] or "", "d_codec": d["codec"] or ""
            })

    # Save cache back
    save_cache(cache_path, cache)

    # Write report
    report_path = Path(args.report).resolve()
    ensure_dir(report_path.parent)
    with report_path.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = [
            "status","reason","match_type","in_quarantine","music_path","dd_path",
            "m_duration","d_duration","m_size","d_size","m_healthy","d_healthy",
            "m_codec","d_codec"
        ]
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print("\nDone.")
    print(f"Report: {report_path}")
    print("Summary:")
    for k in ["pairs","keep_music","swap_in","both_corrupt","missing_in_music","no_decision","errors","dupe_files"]:
        print(f"  {k}: {totals[k]}")

    problems = [r for r in rows if r["status"] == "BOTH_CORRUPT"]
    if problems:
        print("\nFiles that are corrupted with no better duplicate found:")
        for r in problems:
            print(f"  MUSIC: {r['music_path']}\n     DD: {r['dd_path']}")
    else:
        print("\nNo pairs where both copies failed health checks.")

if __name__ == "__main__":
    main()
