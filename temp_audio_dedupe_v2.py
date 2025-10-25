#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temp_audio_dedupe_v2.py

Scan a root folder (default: /Volumes/dotad/TEMP) for duplicate or near-duplicate audio.
3-tier grouping in order:
  A) EXACT: FLAC stream MD5 (metaflac) or decoded PCM SHA1 (ffmpeg)
  B) FPRINT: Chromaprint/AcoustID via `fpcalc` (hash of fingerprint string)
  C) FUZZY: normalized (artist + title) with duration tolerance (± seconds)

Winner scoring (higher is better): healthy → lossless → longer → higher bitrate → newer mtime.
Losers are moved to a timestamped _TRASH_DUPES_* directory on --commit. Dry-run by default.

Examples:
  ./temp_audio_dedupe_v2.py --root "/Volumes/dotad/TEMP"                     # dry-run
  ./temp_audio_dedupe_v2.py --root "/Volumes/dotad/TEMP" --commit            # move losers
  ./temp_audio_dedupe_v2.py --hash-mode file --commit                        # strict bytes
  ./temp_audio_dedupe_v2.py --no-fp --commit                                 # skip fpcalc tier
  ./temp_audio_dedupe_v2.py --fuzzy-seconds 4 --commit                       # wider fuzzy
  ./temp_audio_dedupe_v2.py --exts ".flac,.m4a,.mp3,.wav" --workers 12

No external Python deps. Uses system tools when present: ffprobe/ffmpeg, flac/metaflac, fpcalc.
"""

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any

PRINT_LOCK = threading.Lock()
def log(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)

def sh_which(cmd: str) -> Optional[str]:
    from shutil import which as _which
    return _which(cmd)

def run(cmd: List[str], stdin=None, text=True, timeout=None) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, input=stdin, capture_output=True, text=text, check=False, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 1, "", str(e)

def human_bytes(n: int) -> str:
    u = ["B","KB","MB","GB","TB","PB"]
    f = float(n); i = 0
    while f >= 1024 and i < len(u)-1:
        f /= 1024.0; i += 1
    return f"{f:.2f} {u[i]}"

HAVE_FFPROBE = bool(sh_which("ffprobe"))
HAVE_FFMPEG  = bool(sh_which("ffmpeg"))
HAVE_FLAC    = bool(sh_which("flac"))
HAVE_METAFLAC= bool(sh_which("metaflac"))
HAVE_FPCALC  = bool(sh_which("fpcalc"))

AUDIO_EXTS = {".flac",".wav",".aiff",".aif",".mp3",".m4a",".aac",".ogg",".opus",".wv",".ape",".wma",".dsf",".tta"}

LOSSLESS_CODECS = {
    # ffprobe stream codec_name values treated as lossless
    "flac","alac","ape","tta","wavpack","wv","pcm_s16le","pcm_s24le","pcm_s32le","pcm_f32le",
    "dts","mlp","truehd","dsd_lsbf","dsd_msbf","dsd_lsbf_planar","dsd_msbf_planar"
}

# ---------- ffprobe helpers ----------
def ffprobe_json(path: Path) -> Dict[str, Any]:
    if not HAVE_FFPROBE:
        return {}
    rc, out, err = run([
        "ffprobe","-v","error","-print_format","json","-show_format","-show_streams", str(path)
    ])
    if rc != 0 or not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}

def extract_media_info(path: Path) -> Dict[str, Any]:
    """
    Returns: {
        duration: float|None,
        codec_name: str|None,
        channels: int|None,
        sample_rate: int|None,
        tags: {lower->value},
        bit_rate: float|None (kbps)
    }
    """
    info = {"duration": None, "codec_name": None, "channels": None, "sample_rate": None,
            "tags": {}, "bit_rate": None}
    j = ffprobe_json(path)
    if not j:
        return info
    # format
    fmt = j.get("format") or {}
    dur = fmt.get("duration")
    if dur:
        try:
            d = float(dur)
            if math.isfinite(d) and d > 0:
                info["duration"] = d
        except ValueError:
            pass
    br = fmt.get("bit_rate")
    if br:
        try:
            info["bit_rate"] = float(br)/1000.0
        except ValueError:
            pass
    tags = {}
    for k, v in (fmt.get("tags") or {}).items():
        tags[k.lower()] = f"{v}".strip()
    info["tags"] = tags
    # first audio stream
    astreams = [s for s in (j.get("streams") or []) if s.get("codec_type")=="audio"]
    if astreams:
        s = astreams[0]
        cn = s.get("codec_name")
        if cn: info["codec_name"] = cn.lower()
        ch = s.get("channels")
        try:
            if ch is not None: info["channels"] = int(ch)
        except Exception:
            pass
        sr = s.get("sample_rate")
        try:
            if sr: info["sample_rate"] = int(sr)
        except Exception:
            pass
        if not info["bit_rate"]:
            br2 = s.get("bit_rate")
            if br2:
                try:
                    info["bit_rate"] = float(br2)/1000.0
                except ValueError:
                    pass
    return info

# ---------- health checks ----------
def check_health(path: Path, ext: str) -> Tuple[bool, str]:
    if ext == ".flac" and HAVE_FLAC:
        rc, _, err = run(["flac","-s","-t",str(path)])
        if rc == 0:
            return True, "flac -t OK"
        return False, f"flac -t FAIL: {err[:200]}"
    if HAVE_FFMPEG:
        rc, _, err = run(["ffmpeg","-v","error","-i",str(path),"-f","null","-","-y"])
        return (rc == 0 and not err), ("ffmpeg OK" if rc == 0 and not err else f"ffmpeg FAIL: {err[:200]}")
    return True, "no health tool"

# ---------- exact hashes ----------
def sha1_file(path: Path, bufsize: int = 2**20) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        while True:
            b = f.read(bufsize)
            if not b: break
            h.update(b)
    return h.hexdigest()

def flac_stream_md5(path: Path) -> Optional[str]:
    if not HAVE_METAFLAC: return None
    rc, out, _ = run(["metaflac","--show-md5sum",str(path)])
    if rc == 0 and out:
        md5 = out.strip().lower()
        if md5 and md5 != "00000000000000000000000000000000":
            return md5
    return None

def pcm_sha1(path: Path) -> Optional[str]:
    if not HAVE_FFMPEG: return None
    # Stable decode: stereo, 16-bit signed little-endian, 44.1kHz (fixed to reduce drift issues)
    cmd = ["ffmpeg","-v","error","-i",str(path),"-ac","2","-ar","44100","-f","s16le","-"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return None
    h = hashlib.sha1()
    while True:
        chunk = proc.stdout.read(1024*1024)
        if not chunk: break
        h.update(chunk)
    proc.communicate()
    return h.hexdigest()

# ---------- Chromaprint ----------
def fpcalc_fingerprint(path: Path) -> Optional[str]:
    if not HAVE_FPCALC: return None
    # Prefer JSON output if supported
    rc, out, err = run(["fpcalc","-json",str(path)])
    if rc == 0 and out:
        try:
            j = json.loads(out)
            fp = j.get("fingerprint")
            if fp: return hashlib.sha1(fp.encode("utf-8")).hexdigest()
        except json.JSONDecodeError:
            pass
    # Plain text fallback
    rc, out, err = run(["fpcalc",str(path)])
    if rc == 0 and out:
        # output lines like: "DURATION=243" and "FINGERPRINT=<comma-separated ints>"
        m = re.search(r"FINGERPRINT=([0-9,]+)", out)
        if m:
            s = m.group(1)
            return hashlib.sha1(s.encode("utf-8")).hexdigest()
    return None

# ---------- tag normalization ----------
BRACKETS_RX = re.compile(r"[\[\(（【].*?[\]\)）】]")
FEAT_RX     = re.compile(r"\b(feat\.?|ft\.?)\b.*$", re.IGNORECASE)
NONWORD_RX  = re.compile(r"[^a-z0-9]+")
def ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def norm_text(s: str) -> str:
    s = ascii_fold(s or "").lower().strip()
    s = BRACKETS_RX.sub(" ", s)        # drop bracketed extras
    s = FEAT_RX.sub("", s)             # drop trailing "feat. ... "
    s = NONWORD_RX.sub(" ", s)
    s = " ".join(s.split())
    return s

def title_artist_key(tags: Dict[str,str], filename_hint: str) -> Optional[str]:
    t = tags.get("title") or tags.get("tit2") or ""
    a = tags.get("artist") or tags.get("album_artist") or tags.get("tpe1") or ""
    if not (t and a):
        # try filename fallback
        base = Path(filename_hint).stem
        base = base.replace("_"," ").replace("-", " ")
        base = ascii_fold(base)
        base = " ".join(base.split())
        if not t: t = base
        if not a: a = ""
    nt = norm_text(t)
    na = norm_text(a)
    if not nt:
        return None
    return f"{na}|{nt}"

# ---------- scanning ----------
def walk_audio(root: Path, exts: set) -> List[Path]:
    paths = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip any prior trash dirs
        if any(part.startswith("_TRASH_DUPES") for part in Path(dirpath).parts):
            continue
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                paths.append(p)
    return paths

# ---------- per-file inspection ----------
def inspect_one(path: Path, hash_mode: str, use_fp: bool) -> Dict[str, Any]:
    ext = path.suffix.lower()
    try:
        st = path.stat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False, "error": "missing"}
    size = st.st_size
    mtime = st.st_mtime

    media = extract_media_info(path)
    duration = media.get("duration")
    codec   = (media.get("codec_name") or "").lower() or None
    is_lossless = bool(codec and codec in LOSSLESS_CODECS)
    bitrate_kbps = media.get("bit_rate")
    tags = media.get("tags") or {}

    if not bitrate_kbps and duration and duration > 0:
        bitrate_kbps = (size * 8.0 / duration) / 1000.0

    healthy, health_note = check_health(path, ext)

    # exact key
    key_type = None
    key_val  = None
    if hash_mode == "file":
        key_type, key_val = "FILE", sha1_file(path)
    else:
        md5 = flac_stream_md5(path) if ext == ".flac" else None
        if md5:
            key_type, key_val = "AUD", md5
        else:
            pcm = pcm_sha1(path)
            if pcm:
                key_type, key_val = "AUD", pcm
            else:
                key_type, key_val = "FILE", sha1_file(path)

    # fprint
    fprint = fpcalc_fingerprint(path) if use_fp else None

    # fuzzy tag key
    tkey = title_artist_key(tags, path.name)

    return {
        "path": str(path),
        "ext": ext,
        "exists": True,
        "size": size,
        "mtime": mtime,
        "duration": duration,
        "bitrate_kbps": bitrate_kbps,
        "codec": codec,
        "is_lossless": is_lossless,
        "healthy": healthy,
        "health_note": health_note,
        "exact_key_type": key_type,     # "AUD" or "FILE"
        "exact_key_val": key_val,
        "fprint": fprint,               # sha1 of chromaprint string
        "tag_key": tkey,                # normalized "artist|title"
    }

def score(item: Dict[str,Any]) -> Tuple:
    return (
        1 if item.get("healthy") else 0,
        1 if item.get("is_lossless") else 0,
        round(item.get("duration") or 0.0, 3),
        round(item.get("bitrate_kbps") or 0.0, 3),
        item.get("mtime") or 0.0
    )

def choose_winner(items: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    return sorted(items, key=score, reverse=True)

# ---------- grouping tiers ----------
def group_exact(items: List[Dict[str,Any]]) -> Dict[str, List[Dict[str,Any]]]:
    g = {}
    for it in items:
        k = it.get("exact_key_val")
        if not k: continue
        g.setdefault(f"EXACT:{k}", []).append(it)
    return {k:v for k,v in g.items() if len(v) > 1}

def group_fprint(items: List[Dict[str,Any]]) -> Dict[str, List[Dict[str,Any]]]:
    g = {}
    for it in items:
        fp = it.get("fprint")
        if not fp: continue
        g.setdefault(f"FPRINT:{fp}", []).append(it)
    return {k:v for k,v in g.items() if len(v) > 1}

def group_fuzzy(items: List[Dict[str,Any]], tol_sec: float) -> Dict[str, List[List[Dict[str,Any]]]]:
    """
    Returns dict keyed by FUZZY:<tag_key> with value = list of clusters (each cluster list size>=2).
    We cluster by duration within ± tol_sec inside same tag_key.
    """
    by_tag = {}
    for it in items:
        tk = it.get("tag_key")
        if not tk: continue
        if it.get("duration") is None: continue
        by_tag.setdefault(tk, []).append(it)
    out: Dict[str, List[List[Dict[str,Any]]]] = {}
    for tk, arr in by_tag.items():
        arr = sorted(arr, key=lambda x: x.get("duration") or 0.0)
        clusters: List[List[Dict[str,Any]]] = []
        cluster: List[Dict[str,Any]] = []
        anchor = None
        for it in arr:
            d = it.get("duration") or 0.0
            if anchor is None:
                anchor = d
                cluster = [it]
            elif abs(d - anchor) <= tol_sec:
                cluster.append(it)
            else:
                if len(cluster) >= 2:
                    clusters.append(cluster)
                anchor = d
                cluster = [it]
        if len(cluster) >= 2:
            clusters.append(cluster)
        if clusters:
            out[f"FUZZY:{tk}"] = clusters
    return out

# ---------- trash ----------
def move_to_trash(src: Path, trash_root: Path) -> Path:
    dest = trash_root / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        stem, suf = dest.stem, dest.suffix
        dest = dest.with_name(f"{stem}__{hashlib.sha1(src.name.encode()).hexdigest()[:8]}{suf}")
    shutil.move(str(src), str(dest))
    return dest

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser(description="Deduplicate audio: exact → fingerprint → fuzzy tags. Keep healthiest.")
    ap.add_argument("--root", default="/Volumes/dotad/TEMP", help="Root folder to scan")
    ap.add_argument("--exts", default=".flac,.mp3,.m4a,.wav,.aiff,.aif,.ogg,.opus,.wv,.ape,.wma,.dsf,.tta",
                    help="Comma-separated extensions")
    ap.add_argument("--workers", type=int, default=8, help="Inspector workers (I/O bound)")
    ap.add_argument("--hash-mode", choices=["auto","file"], default="auto",
                    help="auto: FLAC MD5/PCM hash; file: raw file SHA1")
    ap.add_argument("--commit", action="store_true", help="Move losers to trash dir")
    ap.add_argument("--trash-dir", default=None, help="Override trash dir")
    ap.add_argument("--report-csv", default=None, help="Override report path")
    ap.add_argument("--no-fp", action="store_true", help="Disable Chromaprint tier even if fpcalc exists")
    ap.add_argument("--fuzzy-seconds", type=float, default=2.0, help="Duration tolerance for FUZZY tier")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        log(f"ERROR: not a directory: {root}"); sys.exit(2)

    exts = {e.strip().lower() if e.strip().startswith(".") else "."+e.strip().lower()
            for e in args.exts.split(",") if e.strip()}
    exts = exts & AUDIO_EXTS if exts else AUDIO_EXTS

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_dir = Path(args.trash_dir) if args.trash_dir else (root / f"_TRASH_DUPES_{ts}")
    report_csv = Path(args.report_csv) if args.report_csv else (root / f"_DEDUP_REPORT_{ts}.csv")
    use_fp = (not args.no_fp) and HAVE_FPCALC

    log(f"Root: {root}")
    log(f"Exts: {', '.join(sorted(exts))}")
    log(f"Workers: {args.workers}")
    log(f"Hash mode: {args.hash_mode}")
    log(f"Tools: ffprobe={HAVE_FFPROBE} ffmpeg={HAVE_FFMPEG} flac={HAVE_FLAC} metaflac={HAVE_METAFLAC} fpcalc={HAVE_FPCALC}")
    log(f"Chromaprint tier: {'ON' if use_fp else 'OFF'}")
    log(f"Fuzzy duration ±{args.fuzzy_seconds:.2f}s")
    log("Mode: DRY-RUN" if not args.commit else f"Mode: COMMIT → {trash_dir}")

    files = walk_audio(root, exts)
    total = len(files)
    if not total:
        log("No audio files found."); return
    log(f"Found {total} files. Inspecting…")

    interrupted = False
    def on_sigint(signum, frame):
        nonlocal interrupted
        interrupted = True
        log("\nInterrupted: finishing current tasks and writing partial report.")
    signal.signal(signal.SIGINT, on_sigint)

    results: List[Dict[str,Any]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(inspect_one, p, args.hash_mode, use_fp): p for p in files}
        done = 0
        for fut in as_completed(futs):
            if interrupted: break
            res = fut.result()
            results.append(res)
            done += 1
            if done % 50 == 0:
                log(f"… {done}/{total}")

    # ---------- TIER A: EXACT ----------
    remaining = [r for r in results if r.get("exists")]
    exact_groups = group_exact(remaining)
    grouped_paths = set()
    plan_rows: List[Dict[str,Any]] = []
    kept = moved = 0

    def append_group(gkey: str, method: str, items: List[Dict[str,Any]]):
        nonlocal kept, moved
        ordered = choose_winner(items)
        for idx, it in enumerate(ordered):
            action = "keep" if idx==0 else ("move" if args.commit else "would-move")
            plan_rows.append({
                "group_key": gkey, "method": method,
                "keep": (idx==0),
                "path": it["path"],
                "ext": it["ext"],
                "codec": it.get("codec"),
                "lossless": it.get("is_lossless"),
                "size_bytes": it["size"],
                "size_human": human_bytes(it["size"]),
                "duration_sec": round(it.get("duration") or 0.0, 3),
                "bitrate_kbps": round(it.get("bitrate_kbps") or 0.0, 3),
                "healthy": it.get("healthy"),
                "health_note": it.get("health_note") or "",
                "exact_key_type": it.get("exact_key_type"),
                "action": action,
                "dest": ""
            })
        kept += 1
        for it in items: grouped_paths.add(it["path"])

    for gkey, items in exact_groups.items():
        append_group(gkey, "EXACT", items)

    # ---------- TIER B: FPRINT ----------
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    fprint_groups = group_fprint(remaining) if use_fp else {}
    for gkey, items in fprint_groups.items():
        append_group(gkey, "FPRINT", items)

    # ---------- TIER C: FUZZY ----------
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    fuzzy_map = group_fuzzy(remaining, tol_sec=args.fuzzy_seconds)
    for gkey, clusters in fuzzy_map.items():
        for cluster in clusters:
            append_group(gkey, "FUZZY", cluster)

    # ---------- execute moves ----------
    if args.commit and plan_rows:
        trash_dir.mkdir(parents=True, exist_ok=True)
        for row in plan_rows:
            if row["action"] == "move":
                src = Path(row["path"])
                if src.exists():
                    dest = move_to_trash(src, trash_dir)
                    row["dest"] = str(dest)
                    moved += 1

    # ---------- report ----------
    fieldnames = ["group_key","method","keep","path","ext","codec","lossless","size_bytes","size_human",
                  "duration_sec","bitrate_kbps","healthy","health_note","exact_key_type","action","dest"]
    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in plan_rows:
            w.writerow(row)

    # ---------- summary ----------
    total_groups = len(exact_groups) + len(fprint_groups) + sum(len(v) for v in fuzzy_map.values())
    dry_moves = sum(1 for r in plan_rows if r["action"] == "would-move")
    log("\n--- Summary ---")
    log(f"Files inspected: {len(results)}")
    log(f"Groups (EXACT/FPRINT/FUZZY clusters): {total_groups}")
    log(f"Winners kept: {sum(1 for r in plan_rows if r['keep'])}")
    if args.commit:
        log(f"Moved losers: {moved} → {trash_dir}")
    else:
        log(f"Losers (dry-run): {dry_moves}  (use --commit to move)")
    log(f"Report: {report_csv}")

if __name__ == "__main__":
    main()
