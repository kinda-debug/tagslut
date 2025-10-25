#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
temp_audio_dedupe_v3_1.py

Pipeline (in order):
 A) EXACT: FLAC stream MD5 (metaflac) or decoded PCM SHA1 (ffmpeg)
 B) FPRINT: Chromaprint equality (fpcalc)
 C) FPRINT_SIM: Chromaprint near-similarity with shift tolerance (robust to leading/trailing silence)
 D) FUZZY: tag+title OR filename-derived title, clustered by duration window

Winner scoring: healthy → lossless → longer → higher bitrate → newer mtime.
Dry-run by default; use --commit to move losers to _TRASH_DUPES_<ts>.

Key improvements over v3:
 - Handle fpcalc JSON that returns base64-compressed fingerprint: re-run fpcalc in text mode to get CSV integers.
 - Better filename parsing: derive a title key from the last " - " segment, strip (1)/(2)/track numbers, keep remix/edit/version markers.
 - Safer bracket handling: do NOT drop bracketed bits if they contain "remix/edit/version/mix/extended/radio/club/dub/instrumental".
 - Slightly looser near-sim defaults.

Examples:
  ./temp_audio_dedupe_v3_1.py --root "/Volumes/dotad/TEMP"
  ./temp_audio_dedupe_v3_1.py --root "/Volumes/dotad/TEMP" --commit
  ./temp_audio_dedupe_v3_1.py --root "/Volumes/dotad/TEMP" --fuzzy-seconds 4 --fp-sim-ratio 0.62 --commit
  ./temp_audio_dedupe_v3_1.py --no-fp --commit          # skip Chromaprint tiers
"""
import argparse, csv, datetime as dt, hashlib, json, math, os, re, shutil, signal, subprocess, sys, threading, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Any

# ---------- printing ----------
PRINT_LOCK = threading.Lock()
def log(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)

# ---------- shell utils ----------
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
    u = ["B","KB","MB","GB","TB","PB"]; f = float(n); i = 0
    while f >= 1024 and i < len(u)-1: f /= 1024.0; i += 1
    return f"{f:.2f} {u[i]}"

# ---------- tool presence ----------
HAVE_FFPROBE = bool(sh_which("ffprobe"))
HAVE_FFMPEG  = bool(sh_which("ffmpeg"))
HAVE_FLAC    = bool(sh_which("flac"))
HAVE_METAFLAC= bool(sh_which("metaflac"))
HAVE_FPCALC  = bool(sh_which("fpcalc"))

# ---------- constants ----------
AUDIO_EXTS = {".flac"}
# Will be overwritten by argparse value in main via SEGWIN_SECONDS_DEFAULT if needed.

SEGWIN_SECONDS_DEFAULT = 12.0
def pcm_segment_sha1(path: Path, start_sec: float, dur_sec: float) -> Optional[str]:
    """
    Hash a short PCM slice (s16le, 44.1kHz, stereo) starting at start_sec, lasting dur_sec.
    Returns hex sha1 or None on failure.
    """
    if not HAVE_FFMPEG:
        return None
    # Guard against negative or zero durations
    if dur_sec <= 0:
        return None
    cmd = [
        "ffmpeg","-v","error",
        "-ss", f"{max(0.0, start_sec):.3f}",
        "-i", str(path),
        "-t", f"{dur_sec:.3f}",
        "-ac","2","-ar","44100","-f","s16le","-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return None
    h = hashlib.sha1()
    while True:
        chunk = proc.stdout.read(1024*1024)
        if not chunk:
            break
        h.update(chunk)
    proc.communicate()
    return h.hexdigest()

def segwin_hashes(path: Path, duration: Optional[float], win_seconds: float = 12.0) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Compute hashes for three slices: HEAD, MIDDLE, TAIL.
    If duration is unknown/too small, we still try HEAD (0..win) and TAIL (last win).
    For very short tracks, the windows shrink automatically.
    """
    if duration is None or duration <= 0:
        # try best-effort with only head slice
        h = pcm_segment_sha1(path, 0.0, max(1.0, win_seconds/2.0))
        return (h, None, None)
    w = min(win_seconds, max(1.0, duration / 3.0))
    head_start = 0.0
    mid_start  = max(0.0, (duration - w) / 2.0)
    tail_start = max(0.0, duration - w)
    h1 = pcm_segment_sha1(path, head_start, w)
    h2 = pcm_segment_sha1(path, mid_start,  w)
    h3 = pcm_segment_sha1(path, tail_start, w)
    return (h1, h2, h3)


# ----------- sliding-window and trimmed-head helpers -----------
def pcm_head_trim_hash(path: Path, win_seconds: float = 8.0) -> Optional[str]:
    """
    Hash a short PCM slice after trimming leading silence. Useful when one copy has extra silence.
    """
    if not HAVE_FFMPEG:
        return None
    if win_seconds <= 0:
        return None
    cmd = [
        "ffmpeg","-v","error",
        "-i", str(path),
        "-af","silenceremove=start_periods=1:start_duration=0.30:start_threshold=-40dB",
        "-t", f"{win_seconds:.3f}",
        "-ac","2","-ar","44100","-f","s16le","-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        return None
    h = hashlib.sha1()
    while True:
        chunk = proc.stdout.read(1024*1024)
        if not chunk:
            break
        h.update(chunk)
    proc.communicate()
    return h.hexdigest()

def sliding_hashes(path: Path, duration: Optional[float], win_seconds: float, step_seconds: float, max_slices: int) -> List[str]:
    """
    Produce a list of PCM hashes for a sliding window across the file.
    Starts at 0, then +step, up to duration-win, capped by max_slices.
    """
    if not HAVE_FFMPEG or win_seconds <= 0 or step_seconds <= 0 or max_slices <= 0:
        return []
    dur = float(duration) if (duration is not None and duration > 0) else None
    starts: List[float] = []
    if dur is None:
        starts = [0.0]
    else:
        last_start = max(0.0, dur - win_seconds)
        s = 0.0
        while s <= last_start and len(starts) < max_slices:
            starts.append(round(s, 3))
            s += step_seconds
        if not starts:
            starts = [0.0]
    hashes: List[str] = []
    for s in starts:
        h = pcm_segment_sha1(path, s, win_seconds)
        if h:
            hashes.append(h)
    return hashes
LOSSLESS_CODECS = {"flac","alac","ape","tta","wavpack","wv","pcm_s16le","pcm_s24le","pcm_s32le","pcm_f32le","dts","mlp","truehd","dsd_lsbf","dsd_msbf","dsd_lsbf_planar","dsd_msbf_planar"}

# tokens we should preserve if they appear inside brackets
MIX_TOKENS_RX = re.compile(r"\b(remix|edit|version|mix|extended|radio|club|dub|instrumental)\b", re.IGNORECASE)
# tokens to drop entirely in aggressive mode (treated as same "song")
DROP_MIX_TOKENS_RX = re.compile(r"\b(remix|edit|version|mix|extended|radio|club|dub|instrumental)\b", re.IGNORECASE)

# ---------- ffprobe helpers ----------
def ffprobe_json(path: Path) -> Dict[str, Any]:
    if not HAVE_FFPROBE: return {}
    rc, out, _ = run(["ffprobe","-v","error","-print_format","json","-show_format","-show_streams", str(path)])
    if rc != 0 or not out: return {}
    try: return json.loads(out)
    except json.JSONDecodeError: return {}

def extract_media_info(path: Path) -> Dict[str, Any]:
    info = {"duration": None, "codec_name": None, "channels": None, "sample_rate": None, "tags": {}, "bit_rate": None}
    j = ffprobe_json(path)
    if not j: return info
    fmt = j.get("format") or {}
    dur = fmt.get("duration")
    if dur:
        try:
            d = float(dur)
            if math.isfinite(d) and d > 0: info["duration"] = d
        except ValueError: pass
    br = fmt.get("bit_rate")
    if br:
        try: info["bit_rate"] = float(br)/1000.0
        except ValueError: pass
    tags = {}
    for k,v in (fmt.get("tags") or {}).items():
        tags[k.lower()] = f"{v}".strip()
    info["tags"] = tags
    astreams = [s for s in (j.get("streams") or []) if s.get("codec_type")=="audio"]
    if astreams:
        s = astreams[0]
        cn = s.get("codec_name"); info["codec_name"] = (cn.lower() if cn else None)
        ch = s.get("channels")
        try:
            if ch is not None: info["channels"] = int(ch)
        except Exception: pass
        sr = s.get("sample_rate")
        try:
            if sr: info["sample_rate"] = int(sr)
        except Exception: pass
        if not info["bit_rate"]:
            br2 = s.get("bit_rate")
            if br2:
                try: info["bit_rate"] = float(br2)/1000.0
                except ValueError: pass
    return info

# ---------- health ----------
def check_health(path: Path, ext: str) -> Tuple[bool, str]:
    if ext == ".flac" and HAVE_FLAC:
        rc, _, err = run(["flac","-s","-t",str(path)])
        if rc == 0: return True, "flac -t OK"
        return False, f"flac -t FAIL: {err[:200]}"
    if HAVE_FFMPEG:
        rc, _, err = run(["ffmpeg","-v","error","-i",str(path),"-f","null","-","-y"])
        return (rc==0 and not err), ("ffmpeg OK" if rc==0 and not err else f"ffmpeg FAIL: {err[:200]}")
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
    if rc==0 and out:
        md5 = out.strip().lower()
        if md5 and md5!="0"*32: return md5
    return None

def pcm_sha1(path: Path) -> Optional[str]:
    if not HAVE_FFMPEG: return None
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
def fpcalc_fingerprint(path: Path) -> Tuple[Optional[str], Optional[List[int]]]:
    """
    Returns (fingerprint_hex_for_equality, sequence_of_ints_for_similarity or None).
    Handles JSON(base64) by falling back to plain text CSV integers.
    """
    if not HAVE_FPCALC: return None, None
    # Try JSON first (may be base64 or csv)
    rc, out, _ = run(["fpcalc","-json",str(path)])
    if rc == 0 and out:
        try:
            j = json.loads(out)
            fp = j.get("fingerprint")
            if fp:
                if "," in fp:
                    # JSON provided CSV ints
                    seq = [int(x) for x in fp.split(",") if x]
                    return hashlib.sha1(",".join(map(str,seq)).encode("utf-8")).hexdigest(), seq
                else:
                    # Likely base64-compressed: we'll reuse it for equality only,
                    # but we still need CSV ints -> re-run in text mode.
                    rc2, out2, _ = run(["fpcalc",str(path)])
                    if rc2 == 0 and out2:
                        m = re.search(r"FINGERPRINT=([0-9,]+)", out2)
                        if m:
                            s = m.group(1)
                            seq = [int(x) for x in s.split(",") if x]
                            return hashlib.sha1(fp.encode("utf-8")).hexdigest(), seq
                    # If that failed, at least return equality hash
                    return hashlib.sha1(fp.encode("utf-8")).hexdigest(), None
        except Exception:
            pass
    # Plain text fallback
    rc, out, _ = run(["fpcalc",str(path)])
    if rc == 0 and out:
        m = re.search(r"FINGERPRINT=([0-9,]+)", out)
        if m:
            s = m.group(1)
            seq = [int(x) for x in s.split(",") if x]
            return hashlib.sha1(s.encode("utf-8")).hexdigest(), seq
    return None, None

def fpseq_sim_ratio(a: List[int], b: List[int], max_shift: int = 25, min_overlap: int = 50) -> float:
    """Return max equality ratio across integer sequences with small shifts."""
    if not a or not b: return 0.0
    best = 0.0
    la, lb = len(a), len(b)
    max_shift = min(max_shift, max(1, min(la, lb)//5))
    for shift in range(-max_shift, max_shift+1):
        if shift >= 0:
            i0, j0 = shift, 0
            l = min(la - i0, lb)
        else:
            i0, j0 = 0, -shift
            l = min(la, lb - j0)
        if l <= 0 or l < min_overlap: continue
        eq = 0
        for k in range(l):
            if a[i0 + k] == b[j0 + k]:
                eq += 1
        ratio = eq / float(l)
        if ratio > best:
            best = ratio
            if best >= 0.98: break
    return best

# ---------- text normalization ----------
BRACKETS_RX = re.compile(r"[\[\(（【].*?[\]\)）】]")
FEAT_RX     = re.compile(r"\b(feat\.?|ft\.?)\b.*$", re.IGNORECASE)
NONWORD_RX  = re.compile(r"[^a-z0-9]+")
TRAIL_CNT_RX= re.compile(r"\s*\(\d+\)\s*$")       # trailing " (1)" etc.
TRACKNO_RX  = re.compile(r"^\s*\d{1,2}\.\s*")     # "01. "

def ascii_fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def norm_keep_mix_markers(s: str) -> str:
    s = ascii_fold(s or "")
    # remove brackets ONLY if they don't contain mix markers
    def repl(m):
        inner = m.group(0)
        return inner if MIX_TOKENS_RX.search(inner) else " "
    s = BRACKETS_RX.sub(repl, s)
    s = FEAT_RX.sub("", s)         # drop trailing feat. … entirely
    s = NONWORD_RX.sub(" ", s.lower())
    s = " ".join(s.split())
    return s

# Helper to drop mix/remix/edit/version tokens for aggressive fuzzy matching
def drop_mix_keywords(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    s2 = DROP_MIX_TOKENS_RX.sub(" ", s)
    s2 = " ".join(s2.split())
    return s2 or None

def canonical_filename_key(filename: str) -> Optional[str]:
    base = Path(filename).stem
    base = TRAIL_CNT_RX.sub("", base)         # remove trailing (1), (2)…
    base = base.replace("_"," ").strip()
    s = norm_keep_mix_markers(base)
    return s or None

def canonical_title_from_filename(filename: str) -> Optional[str]:
    """
    Try to pull the 'title' from the last ' - ' segment, keeping remix/edit markers.
    """
    base = Path(filename).stem
    base = TRAIL_CNT_RX.sub("", base)
    parts = [p.strip() for p in base.split(" - ") if p.strip()]
    cand = parts[-1] if parts else base
    cand = TRACKNO_RX.sub("", cand)
    s = norm_keep_mix_markers(cand)
    return s or None

def title_artist_key(tags: Dict[str,str], filename_hint: str) -> Optional[str]:
    t = tags.get("title") or tags.get("tit2") or ""
    a = tags.get("artist") or tags.get("album_artist") or tags.get("tpe1") or ""
    if t:
        nt = norm_keep_mix_markers(t)
        na = norm_keep_mix_markers(a) if a else ""
        if nt:
            return f"{na}|{nt}"
    # fallback to filename-derived title
    ft = canonical_title_from_filename(filename_hint)
    return ft

# ---------- scanning ----------
def walk_audio(root: Path, exts: set) -> List[Path]:
    paths = []
    for dirpath, _, filenames in os.walk(root):
        if any(part.startswith("_TRASH_DUPES") for part in Path(dirpath).parts):
            continue
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                paths.append(p)
    return paths

# ---------- per file ----------
def inspect_one(path: Path, hash_mode: str, use_fp: bool) -> Dict[str, Any]:
    ext = path.suffix.lower()
    try: st = path.stat()
    except FileNotFoundError: return {"path": str(path), "exists": False, "error": "missing"}
    size = st.st_size; mtime = st.st_mtime

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
    if hash_mode == "file":
        exact_type, exact_val = "FILE", sha1_file(path)
    else:
        md5 = flac_stream_md5(path) if ext == ".flac" else None
        if md5:
            exact_type, exact_val = "AUD", md5
        else:
            pcm = pcm_sha1(path)
            exact_type, exact_val = ("AUD", pcm) if pcm else ("FILE", sha1_file(path))

    # fingerprints
    fprint_hex, fseq = (None, None)
    if use_fp:
        fprint_hex, fseq = fpcalc_fingerprint(path)

    # fuzzy keys
    tagkey = title_artist_key(tags, path.name)         # artist|title or filename-title
    filekey = canonical_filename_key(path.name)        # full filename canonical
    # base fuzzy key prefers tag/title; fallback to filename-derived title; then full filename
    base_fuzzy = tagkey or canonical_title_from_filename(path.name) or filekey
    aggr_fuzzy = drop_mix_keywords(base_fuzzy) if base_fuzzy else None

    # corruption-tolerant segment hashes
    seg_h1, seg_h2, seg_h3 = segwin_hashes(path, duration, win_seconds=SEGWIN_SECONDS_DEFAULT)

    return {
        "path": str(path),
        "name": path.name,
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
        "exact_key_type": exact_type,
        "exact_key_val": exact_val,
        "fprint": fprint_hex,
        "fpseq": fseq,
        "seg_h1": seg_h1,
        "seg_h2": seg_h2,
        "seg_h3": seg_h3,
        "tag_key": tagkey,
        "file_key": filekey,
        "fuzzy_key": base_fuzzy,
        "fuzzy_key_aggr": aggr_fuzzy,
    }
def group_segwin(items: List[Dict[str,Any]], min_matches: int) -> List[List[Dict[str,Any]]]:
    """
    Greedy clustering: connect two items if at least `min_matches` of their segment hashes (h1,h2,h3) match.
    """
    pool = []
    for it in items:
        hset = {it.get("seg_h1"), it.get("seg_h2"), it.get("seg_h3")}
        hset.discard(None)
        if hset:
            pool.append((it, hset))
    n = len(pool)
    if n < 2:
        return []
    # Build adjacency by comparing pairwise overlap counts
    adj = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i+1, n):
            si = pool[i][1]; sj = pool[j][1]
            overlap = len(si.intersection(sj))
            if overlap >= min_matches:
                adj[i].add(j)
                adj[j].add(i)
    # Extract connected components
    seen = [False]*n
    clusters: List[List[Dict[str,Any]]] = []
    for i in range(n):
        if seen[i]:
            continue
        q = [i]; seen[i] = True; comp = [pool[i][0]]
        while q:
            u = q.pop()
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    q.append(v)
                    comp.append(pool[v][0])
        if len(comp) >= 2:
            clusters.append(comp)
    return clusters


# ----------- sliding-window/trimmed-head grouping -----------
def group_segwin_sliding(items: List[Dict[str,Any]],
                         win_seconds: float,
                         step_seconds: float,
                         max_slices: int,
                         min_matches: int,
                         include_trim: bool) -> List[List[Dict[str,Any]]]:
    """
    Build clusters by comparing sets of sliding-window hashes (and optional trimmed-head hash).
    Two files connect if they share >= min_matches hashes.
    """
    # Precompute per-item hash sets
    pool_items: List[Dict[str,Any]] = []
    hash_sets: List[set] = []
    for it in items:
        p = it.get("path")
        if not p:
            continue
        hs = set(sliding_hashes(Path(p), it.get("duration"), win_seconds, step_seconds, max_slices))
        if include_trim:
            th = pcm_head_trim_hash(Path(p), win_seconds=min(win_seconds, 8.0))
            if th:
                hs.add(f"TRIM:{th}")
        if hs:
            pool_items.append(it)
            hash_sets.append(hs)
    n = len(pool_items)
    if n < 2:
        return []
    # Pairwise overlaps
    adj = [set() for _ in range(n)]
    for i in range(n):
        si = hash_sets[i]
        for j in range(i+1, n):
            sj = hash_sets[j]
            if len(si.intersection(sj)) >= min_matches:
                adj[i].add(j); adj[j].add(i)
    # Connected components
    seen = [False]*n
    clusters: List[List[Dict[str,Any]]] = []
    for i in range(n):
        if seen[i]:
            continue
        q = [i]; seen[i] = True; comp = [pool_items[i]]
        while q:
            u = q.pop()
            for v in adj[u]:
                if not seen[v]:
                    seen[v] = True
                    q.append(v)
                    comp.append(pool_items[v])
        if len(comp) >= 2:
            clusters.append(comp)
    return clusters

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

# ---------- grouping ----------
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

def group_fprint_sim(items: List[Dict[str,Any]], ratio: float, max_shift: int, min_overlap: int) -> List[List[Dict[str,Any]]]:
    pool = [it for it in items if it.get("fpseq")]
    used = set()
    clusters: List[List[Dict[str,Any]]] = []
    for i, it in enumerate(pool):
        if i in used: continue
        base = it
        cluster = [base]
        used.add(i)
        for j in range(i+1, len(pool)):
            if j in used: continue
            other = pool[j]
            r = fpseq_sim_ratio(base["fpseq"], other["fpseq"], max_shift=max_shift, min_overlap=min_overlap)
            if r >= ratio:
                cluster.append(other)
                used.add(j)
        if len(cluster) >= 2:
            clusters.append(cluster)
    return clusters

def group_fuzzy(items: List[Dict[str,Any]], tol_sec: float, aggressive: bool) -> List[List[Dict[str,Any]]]:
    by_key: Dict[str, List[Dict[str,Any]]] = {}
    for it in items:
        # prefer consolidated fuzzy key; in aggressive mode drop remix/edit keywords
        k = (it.get("fuzzy_key_aggr") if aggressive else it.get("fuzzy_key")) or it.get("file_key")
        if not k: continue
        if it.get("duration") is None: continue
        by_key.setdefault(k, []).append(it)
    clusters: List[List[Dict[str,Any]]] = []
    for k, arr in by_key.items():
        arr = sorted(arr, key=lambda x: x.get("duration") or 0.0)
        group = []
        anchor = None
        for it in arr:
            d = it.get("duration") or 0.0
            if anchor is None:
                anchor = d; group = [it]
                continue
            if abs(d - anchor) <= tol_sec:
                group.append(it)
            else:
                if len(group) >= 2:
                    clusters.append(group)
                anchor = d; group = [it]
        if len(group) >= 2:
            clusters.append(group)
    return clusters

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
    global SEGWIN_SECONDS_DEFAULT
    ap = argparse.ArgumentParser(description="Deduplicate audio: exact → fingerprint → fingerprint-sim → fuzzy. Keep healthiest.")
    ap.add_argument("--root", default="/Volumes/dotad/TEMP", help="Root folder to scan")
    ap.add_argument("--exts", default=".flac", help="Comma-separated extensions (FLAC only in this build)")
    ap.add_argument("--workers", type=int, default=8, help="Inspector workers (I/O bound)")
    ap.add_argument("--hash-mode", choices=["auto","file"], default="auto", help="auto: FLAC MD5/PCM hash; file: raw file SHA1")
    ap.add_argument("--commit", action="store_true", help="Move losers to trash dir")
    ap.add_argument("--trash-dir", default=None, help="Override trash dir")
    ap.add_argument("--report-csv", default=None, help="Override report path")
    ap.add_argument("--no-fp", action="store_true", help="Disable Chromaprint tiers even if fpcalc exists")
    ap.add_argument("--fuzzy-seconds", type=float, default=2.0, help="Duration tolerance for FUZZY tier")
    # fingerprint similarity parameters (loosened)
    ap.add_argument("--fp-sim-ratio", type=float, default=0.62, help="Min equality ratio for fingerprint near-sim (0..1)")
    ap.add_argument("--fp-sim-shift", type=int, default=25, help="Max shift (subfingerprint steps) to consider")
    ap.add_argument("--fp-sim-min-overlap", type=int, default=50, help="Min overlapped length to consider")
    ap.add_argument("--aggressive", action="store_true",
                    help="Collapse by title only (ignore remix/edit keywords) in FUZZY stage; widens fuzzy window if left at default")
    # segment-window parameters
    ap.add_argument("--segwin-seconds", type=float, default=SEGWIN_SECONDS_DEFAULT,
                    help="Seconds per segment for corruption-tolerant matching (head/middle/tail)")
    ap.add_argument("--segwin-min-matches", type=int, default=2,
                    help="Minimum number of matching segments (0..3) required to group (default: 2)")
    ap.add_argument("--no-segwin", action="store_true",
                    help="Disable corruption-tolerant segment-window matching")
    ap.add_argument("--segwin-sliding", action="store_true",
                    help="Enable sliding-window content matching across the track")
    ap.add_argument("--segwin-step", type=float, default=4.0,
                    help="Seconds between sliding windows (default: 4.0)")
    ap.add_argument("--segwin-max-slices", type=int, default=20,
                    help="Maximum number of sliding windows per file (default: 20)")
    ap.add_argument("--segwin-trim-head", action="store_true",
                    help="Also compare a silence-trimmed head hash to align copies with extra leading silence")

    args = ap.parse_args()

    SEGWIN_SECONDS_DEFAULT = float(args.segwin_seconds)

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

    # If aggressive and user did not override the default fuzzy window, widen it
    if args.aggressive and abs(args.fuzzy_seconds - 2.0) < 1e-9:
        args.fuzzy_seconds = 30.0

    log(f"Root: {root}")
    log(f"Exts: {', '.join(sorted(exts))}")
    log(f"Workers: {args.workers}")
    log(f"Hash mode: {args.hash_mode}")
    log(f"Tools: ffprobe={HAVE_FFPROBE} ffmpeg={HAVE_FFMPEG} flac={HAVE_FLAC} metaflac={HAVE_METAFLAC} fpcalc={HAVE_FPCALC}")
    log(f"Chromaprint tiers: {'ON' if use_fp else 'OFF'} (eq + near-sim)")
    log(f"FPRINT_SIM params: ratio≥{args.fp_sim_ratio:.2f}, shift≤{args.fp_sim_shift}, overlap≥{args.fp_sim_min_overlap}")
    log(f"Fuzzy duration window: ±{args.fuzzy_seconds:.2f}s")
    log(f"SEGWIN: {'ON' if not args.no_segwin else 'OFF'} (win={args.segwin_seconds:.1f}s, min_matches={args.segwin_min_matches})")
    log(f"SEGWIN_SLIDING: {'ON' if args.segwin_sliding else 'OFF'} (step={args.segwin_step:.1f}s, max_slices={args.segwin_max_slices}, trim_head={'ON' if args.segwin_trim_head else 'OFF'})")
    log(f"Aggressive FUZZY: {'ON' if args.aggressive else 'OFF'}")
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

    # Stage book-keeping
    remaining = [r for r in results if r.get("exists")]
    grouped_paths = set()
    plan_rows: List[Dict[str,Any]] = []
    kept_groups = moved = 0

    def add_group(method: str, group_key: str, items: List[Dict[str,Any]]):
        nonlocal kept_groups
        ordered = choose_winner(items)
        for idx, it in enumerate(ordered):
            action = "keep" if idx==0 else ("move" if args.commit else "would-move")
            plan_rows.append({
                "group_key": f"{method}:{group_key}",
                "method": method,
                "keep": (idx==0),
                "path": it["path"],
                "name": it["name"],
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
        kept_groups += 1
        for it in items:
            grouped_paths.add(it["path"])

    # A) EXACT
    exact_groups = group_exact(remaining)
    for k, items in exact_groups.items():
        add_group("EXACT", k[6:], items)

    # B) FPRINT equality
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    if use_fp:
        eq_groups = group_fprint(remaining)
        for k, items in eq_groups.items():
            add_group("FPRINT", k[7:], items)

    # C) FPRINT near-similarity
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    if use_fp:
        sim_clusters = group_fprint_sim(remaining, ratio=args.fp_sim_ratio,
                                        max_shift=args.fp_sim_shift,
                                        min_overlap=args.fp_sim_min_overlap)
        for idx, cluster in enumerate(sim_clusters, start=1):
            add_group("FPRINT_SIM", f"cluster{idx}", cluster)

    # D) SEGWIN (corruption-tolerant segment hashes)
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    if not args.no_segwin:
        seg_clusters = group_segwin(remaining, min_matches=args.segwin_min_matches)
        for idx, cluster in enumerate(seg_clusters, start=1):
            add_group("SEGWIN", f"cluster{idx}", cluster)

    # D2) SEGWIN_SLIDE (sliding-window / trimmed-head)
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    if not args.no_segwin and args.segwin_sliding:
        segs_clusters = group_segwin_sliding(remaining,
                                             win_seconds=args.segwin_seconds,
                                             step_seconds=args.segwin_step,
                                             max_slices=args.segwin_max_slices,
                                             min_matches=args.segwin_min_matches,
                                             include_trim=args.segwin_trim_head)
        for idx, cluster in enumerate(segs_clusters, start=1):
            add_group("SEGWIN_SLIDE", f"cluster{idx}", cluster)

    # E) FUZZY (tags or filename-derived title) + duration
    remaining = [r for r in remaining if r["path"] not in grouped_paths]
    fuzzy_clusters = group_fuzzy(remaining, tol_sec=args.fuzzy_seconds, aggressive=args.aggressive)
    for idx, cluster in enumerate(fuzzy_clusters, start=1):
        add_group("FUZZY_AGGR" if args.aggressive else "FUZZY", f"cluster{idx}", cluster)

    # Execute moves
    if args.commit and plan_rows:
        trash_dir.mkdir(parents=True, exist_ok=True)
        for row in plan_rows:
            if row["action"] == "move":
                src = Path(row["path"])
                if src.exists():
                    dest = move_to_trash(src, trash_dir)
                    row["dest"] = str(dest)
                    moved += 1

    # Report
    fieldnames = ["group_key","method","keep","path","name","ext","codec","lossless","size_bytes","size_human",
                  "duration_sec","bitrate_kbps","healthy","health_note","exact_key_type","action","dest"]
    with open(report_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in plan_rows:
            w.writerow(row)

    # Summary
    dry_moves = sum(1 for r in plan_rows if r["action"] == "would-move")
    log("\n--- Summary ---")
    log(f"Files inspected: {len(results)}")
    log(f"Groups formed: {sum(1 for r in plan_rows if r['keep'])}")
    log(f"Chromaprint near-sim clusters: {len([1 for r in plan_rows if r['keep'] and r['method']=='FPRINT_SIM'])}")
    if args.commit:
        log(f"Moved losers: {moved} → {trash_dir}")
    else:
        log(f"Losers (dry-run): {dry_moves}  (use --commit to move)")
    log(f"Report: {report_csv}")

if __name__ == "__main__":
    main()
