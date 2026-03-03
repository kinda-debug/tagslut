#!/usr/bin/env python3
"""
tagslut_dj_prepare.py

Rekordbox-optimized DJ prep pipeline:

Core principle (per Georges): Only regenerate MP3 if it's suboptimal.
- If source is already an optimal Rekordbox-safe MP3: copy as-is.
- If source is lossless (FLAC/AIFF/WAV/ALAC): convert to MP3 320 CBR.
- If source is MP3 but suboptimal: try to find a lossless candidate in library; if none, re-encode (compatibility upgrade).

Key changes vs older approach:
- Parse Rekordbox XML first.
- Probe ONLY DJ targets (not the entire library).
- Optional fallback resolver scans library for basenames only when XML paths are missing/broken.

Outputs:
  <out-root>/
    LIBRARY/<Artist>/<Album>/<nn - Title>.mp3
    REPORTS/run_YYYYmmdd_HHMMSS/
      summary.json
      decisions.csv
      unresolved.csv
      duplicates.csv
      logs.txt
    DUPES/run_YYYYmmdd_HHMMSS/   (duplicates moved here)

Requires:
  - ffmpeg
  - ffprobe
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


AUDIO_EXTS = {".flac", ".wav", ".aiff", ".aif", ".m4a", ".alac", ".mp3", ".aac", ".ogg"}
LOSSLESS_EXTS = {".flac", ".wav", ".aiff", ".aif"}  # ALAC treated as lossless by codec, not ext

ILLEGAL_FS_CHARS = r'[/\\:*?"<>|]'
WS_RE = re.compile(r"\s+")
DJ_XML_LOCATION_PREFIXES = ("file://localhost/", "file:///", "file:")

DEFAULT_MAX_WORKERS = 8


# -------------------------
# Console / logging
# -------------------------

def vprint(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg, flush=True)


def now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def run_cmd(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


# -------------------------
# Text normalization
# -------------------------

def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def sanitize_component(s: str, fallback: str = "Unknown") -> str:
    s = nfc(s).strip()
    s = re.sub(ILLEGAL_FS_CHARS, "_", s)
    s = WS_RE.sub(" ", s).strip()
    s = s.rstrip(" .")
    return s if s else fallback


def normalize_key(s: str) -> str:
    """Loose key for matching."""
    s = nfc(s or "").strip().lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^\w\s'-]+", " ", s)
    s = WS_RE.sub(" ", s).strip()
    return s


# -------------------------
# Rekordbox XML parsing
# -------------------------

@dataclass(frozen=True)
class RBTrack:
    location: Optional[str]     # absolute file path (decoded) if present
    name: str
    artist: str
    album: str
    track_number: Optional[int]
    year: Optional[str]
    bpm: Optional[str]
    key: Optional[str]
    duration_sec: Optional[float]  # seconds if present
    genre: Optional[str]


def _decode_rb_location(loc: str) -> Optional[str]:
    if not loc:
        return None
    loc = loc.strip()
    # Rekordbox uses "file://localhost/..." or "file:///..."
    for pfx in DJ_XML_LOCATION_PREFIXES:
        if loc.startswith(pfx):
            loc = loc[len(pfx):]
            break
    loc = urllib.parse.unquote(loc)

    # Some XML exports include Windows paths or volume-less paths; we only accept absolute POSIX here
    if loc.startswith("/"):
        return nfc(loc)
    return None


def parse_rekordbox_xml(xml_path: Path, verbose: bool) -> List[RBTrack]:
    t0 = time.time()
    tree = ET.parse(str(xml_path))
    root = tree.getroot()

    tracks: List[RBTrack] = []

    # Rekordbox exports typically: <DJ_PLAYLISTS><COLLECTION><TRACK ... Location="file://..."/>
    collection = root.find(".//COLLECTION")
    if collection is None:
        raise RuntimeError("Could not find <COLLECTION> in Rekordbox XML.")

    for tr in collection.findall("TRACK"):
        loc = _decode_rb_location(tr.get("Location", "") or "")
        name = tr.get("Name", "") or ""
        artist = tr.get("Artist", "") or ""
        album = tr.get("Album", "") or ""
        tn = tr.get("TrackNumber", "")
        year = tr.get("Year", "") or ""
        bpm = tr.get("AverageBpm", "") or tr.get("BPM", "") or ""
        key = tr.get("Tonality", "") or tr.get("Key", "") or ""
        genre = tr.get("Genre", "") or ""

        # Duration often in milliseconds or seconds depending on export; we attempt both
        dur_raw = tr.get("TotalTime", "") or tr.get("Length", "") or ""
        dur_sec: Optional[float] = None
        if dur_raw:
            try:
                v = float(dur_raw)
                # Heuristic: if > 10000 it's probably ms
                dur_sec = v / 1000.0 if v > 10000 else v
            except Exception:
                dur_sec = None

        track_number = None
        if tn:
            try:
                track_number = int(float(tn))
            except Exception:
                track_number = None

        year = year.strip() if year.strip() else None
        bpm = bpm.strip() if bpm.strip() else None
        key = key.strip() if key.strip() else None
        genre = genre.strip() if genre.strip() else None

        tracks.append(
            RBTrack(
                location=loc,
                name=nfc(name),
                artist=nfc(artist),
                album=nfc(album),
                track_number=track_number,
                year=year,
                bpm=bpm,
                key=key,
                duration_sec=dur_sec,
                genre=genre,
            )
        )

    vprint(f"[XML] Loaded {len(tracks)} tracks from {xml_path} in {time.time()-t0:.2f}s", verbose)
    return tracks


# -------------------------
# Media probing
# -------------------------

@dataclass
class MediaInfo:
    path: Path
    codec: str
    duration: float
    sample_rate: Optional[int]
    channels: Optional[int]
    bit_rate: Optional[int]        # stream bitrate if present
    format_bit_rate: Optional[int] # container bitrate if present
    has_attached_pic: bool
    tags: Dict[str, str]


def ffprobe_json(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-print_format", "json",
        str(path),
    ]
    p = run_cmd(cmd)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or f"ffprobe failed: {path}")
    return json.loads(p.stdout)


def extract_media_info(path: Path) -> MediaInfo:
    data = ffprobe_json(path)
    fmt = data.get("format", {}) or {}
    streams = data.get("streams", []) or []

    duration = float(fmt.get("duration", 0) or 0.0)

    audio = None
    for s in streams:
        if s.get("codec_type") == "audio":
            audio = s
            break
    if audio is None:
        raise RuntimeError(f"No audio stream: {path}")

    codec = (audio.get("codec_name") or "").lower()

    sr = audio.get("sample_rate")
    sample_rate = int(sr) if sr else None

    ch = audio.get("channels")
    channels = int(ch) if ch else None

    br = audio.get("bit_rate")
    bit_rate = int(br) if br else None

    fbr = fmt.get("bit_rate")
    format_bit_rate = int(fbr) if fbr else None

    has_attached_pic = False
    for s in streams:
        if s.get("codec_type") == "video" and int(s.get("disposition", {}).get("attached_pic", 0) or 0) == 1:
            has_attached_pic = True
            break

    tags = {str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()}
    return MediaInfo(
        path=path,
        codec=codec,
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        bit_rate=bit_rate,
        format_bit_rate=format_bit_rate,
        has_attached_pic=has_attached_pic,
        tags=tags,
    )


# -------------------------
# HF "fake 320" check (optional)
# -------------------------

def hf_rms_db(path: Path) -> Optional[float]:
    """
    High-frequency RMS after a highpass at 18k.
    Lower (more negative) values can indicate aggressive lowpass.
    This is heuristic and should be used only as a "suboptimal" signal.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-v", "error",
        "-i", str(path),
        "-af", "highpass=f=18000,astats=metadata=0:reset=0:measure_overall=1",
        "-f", "null", "-"
    ]
    p = run_cmd(cmd)
    if p.returncode != 0:
        return None
    m = re.findall(r"RMS level dB:\s*([-0-9.]+)", p.stderr)
    if not m:
        return None
    try:
        return float(m[-1])
    except Exception:
        return None


# -------------------------
# Classification
# -------------------------

@dataclass(frozen=True)
class ClassifyResult:
    is_lossless: bool
    is_mp3: bool
    is_optimal_mp3: bool
    is_suboptimal: bool
    reasons: List[str]
    hf_rms_db: Optional[float]


def classify_for_rekordbox(mi: MediaInfo, do_hf_check: bool, hf_threshold_db: float) -> ClassifyResult:
    reasons: List[str] = []

    is_mp3 = (mi.codec == "mp3")
    is_lossless = (mi.path.suffix.lower() in LOSSLESS_EXTS) or (mi.codec == "alac")

    hf_val: Optional[float] = None

    # Lossless always needs conversion
    if is_lossless and not is_mp3:
        return ClassifyResult(
            is_lossless=True,
            is_mp3=False,
            is_optimal_mp3=False,
            is_suboptimal=True,
            reasons=["lossless_source"],
            hf_rms_db=None,
        )

    if not is_mp3:
        # AAC/OGG/etc => suboptimal for Rekordbox USB workflows; convert to MP3
        reasons.append(f"codec:{mi.codec}")
        return ClassifyResult(
            is_lossless=False,
            is_mp3=False,
            is_optimal_mp3=False,
            is_suboptimal=True,
            reasons=reasons,
            hf_rms_db=None,
        )

    # MP3 branch
    # We want: 44.1kHz, stereo, and ~320kbps (CBR preferred, but we use bitrate heuristic).
    sr = mi.sample_rate or 0
    ch = mi.channels or 0
    br = mi.bit_rate or mi.format_bit_rate or 0

    if sr != 44100:
        reasons.append(f"sample_rate:{sr}")
    if ch != 2:
        reasons.append(f"channels:{ch}")

    # Bitrate heuristic:
    # - If < 300k => definitely suboptimal
    # - If 300k..319k => suboptimal
    # - If ~320k => potentially optimal
    if br < 300_000:
        reasons.append(f"bitrate:{br}")
    elif br < 319_000:
        reasons.append(f"bitrate:{br}")

    # Optional HF check only for "nominally 320k" MP3s
    if do_hf_check and (br >= 319_000):
        hf_val = hf_rms_db(mi.path)
        if hf_val is not None and hf_val < hf_threshold_db:
            reasons.append(f"hf_low:{hf_val:.2f}dB<th{hf_threshold_db:.2f}")

    is_optimal = (len(reasons) == 0) and (br >= 319_000) and (sr == 44100) and (ch == 2)
    is_suboptimal = not is_optimal

    return ClassifyResult(
        is_lossless=False,
        is_mp3=True,
        is_optimal_mp3=is_optimal,
        is_suboptimal=is_suboptimal,
        reasons=reasons if reasons else (["optimal"] if is_optimal else ["unknown"]),
        hf_rms_db=hf_val,
    )


# -------------------------
# Resolving library paths
# -------------------------

def build_basename_set(rb_tracks: List[RBTrack]) -> Set[str]:
    names: Set[str] = set()
    for t in rb_tracks:
        if t.location:
            names.add(Path(t.location).name)
    return names


def scan_library_for_basenames(in_root: Path, needed: Set[str], verbose: bool) -> Dict[str, List[Path]]:
    """
    Fallback resolver:
    - Walk the library but only record hits whose basename is in 'needed'.
    - Returns mapping basename -> [paths...]
    """
    hits: Dict[str, List[Path]] = {bn: [] for bn in needed}
    if not needed:
        return hits

    vprint(f"[RESOLVE] Fallback scan in library for {len(needed)} basenames...", verbose)
    t0 = time.time()
    seen = 0
    for root, dirs, files in os.walk(in_root):
        seen += 1
        for fn in files:
            if fn in needed:
                p = Path(root) / fn
                if p.suffix.lower() in AUDIO_EXTS:
                    hits[fn].append(p)
        if verbose and seen % 500 == 0:
            vprint(f"[RESOLVE] walked {seen} dirs...", verbose)

    vprint(f"[RESOLVE] Fallback scan done in {time.time()-t0:.2f}s", verbose)
    return hits


def resolve_targets(
    rb_tracks: List[RBTrack],
    in_root: Path,
    verbose: bool,
    do_fallback_scan: bool,
) -> Tuple[List[Tuple[RBTrack, Path]], List[RBTrack]]:
    """
    Resolution strategy:
    1) If XML location exists and file exists -> accept.
    2) Else unresolved. If do_fallback_scan:
       - Try matching by basename inside the library.
       - If multiple hits, keep all for later probing; we choose best candidate by metadata/duration.
    """
    resolved: List[Tuple[RBTrack, Path]] = []
    unresolved: List[RBTrack] = []

    missing: List[RBTrack] = []
    for t in rb_tracks:
        if t.location:
            p = Path(t.location)
            if p.exists():
                resolved.append((t, p))
            else:
                missing.append(t)
        else:
            missing.append(t)

    if not missing:
        vprint(f"[RESOLVE] Resolved {len(resolved)} via XML Location paths. Unresolved 0.", verbose)
        return resolved, unresolved

    vprint(f"[RESOLVE] Resolved {len(resolved)} via XML Location. Missing/unresolved {len(missing)}.", verbose)

    if not do_fallback_scan:
        unresolved.extend(missing)
        return resolved, unresolved

    # Fallback: scan library for the missing basenames
    needed_basenames = set()
    for t in missing:
        if t.location:
            needed_basenames.add(Path(t.location).name)

    hits = scan_library_for_basenames(in_root, needed_basenames, verbose)

    for t in missing:
        if t.location:
            bn = Path(t.location).name
            candidates = hits.get(bn) or []
            if not candidates:
                unresolved.append(t)
            else:
                # Keep all candidates; we add multiple resolved pairs
                for p in candidates:
                    resolved.append((t, p))
        else:
            unresolved.append(t)

    vprint(f"[RESOLVE] After fallback: resolved={len(resolved)} unresolved={len(unresolved)}", verbose)
    return resolved, unresolved


# -------------------------
# Output naming / layout
# -------------------------

def build_output_path(out_library_root: Path, rb: RBTrack, mi: MediaInfo) -> Path:
    artist = sanitize_component(rb.artist or mi.tags.get("artist", ""), "Unknown Artist")
    album = sanitize_component(rb.album or mi.tags.get("album", ""), "Unknown Album")

    title = sanitize_component(rb.name or mi.tags.get("title", mi.path.stem), mi.path.stem)

    # Track number: prefer XML, else tags
    tn = rb.track_number
    if tn is None:
        tn_raw = mi.tags.get("track", "") or mi.tags.get("tracknumber", "")
        try:
            tn = int(str(tn_raw).split("/")[0])
        except Exception:
            tn = None

    prefix = f"{tn:02d} - " if tn is not None else ""
    fname = sanitize_component(f"{prefix}{title}", title) + ".mp3"

    return out_library_root / artist / album / fname


# -------------------------
# Artwork discovery
# -------------------------

def find_folder_art(path: Path) -> Optional[Path]:
    """
    Look for common cover files in the same directory as the audio.
    """
    folder = path.parent
    candidates = [
        "cover.jpg", "Cover.jpg", "folder.jpg", "Folder.jpg",
        "front.jpg", "Front.jpg", "art.jpg", "Art.jpg",
        "cover.png", "Cover.png", "folder.png", "Folder.png",
    ]
    for c in candidates:
        p = folder / c
        if p.exists() and p.is_file():
            return p
    return None


# -------------------------
# Conversion / copy
# -------------------------

def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path, verbose: bool) -> None:
    ensure_parent(dst)
    # Copy with metadata (mtime, etc.)
    shutil.copy2(src, dst)
    vprint(f"[COPY] {src} -> {dst}", verbose)


def convert_to_mp3_320(
    src: Path,
    dst: Path,
    *,
    prefer_folder_art: bool,
    verbose: bool
) -> Tuple[bool, str]:
    """
    Convert src to MP3 320 CBR, Rekordbox-safe.
    Embeds art from:
      - existing attached_pic stream if present
      - else folder art if prefer_folder_art and available
    """
    ensure_parent(dst)

    # We use ffprobe to know if attached pic exists
    try:
        mi = extract_media_info(src)
    except Exception as e:
        return False, f"ffprobe_failed:{e}"

    art_path: Optional[Path] = None
    if not mi.has_attached_pic and prefer_folder_art:
        art_path = find_folder_art(src)

    cmd: List[str] = ["ffmpeg", "-hide_banner", "-y", "-i", str(src)]

    # If we have external art, add it as second input
    if art_path is not None:
        cmd += ["-i", str(art_path)]

    # Map audio
    cmd += ["-map", "0:a:0"]

    # Map art
    if mi.has_attached_pic:
        # If src has attached picture as video stream, map it
        cmd += ["-map", "0:v?"]
    elif art_path is not None:
        # Map external art input
        cmd += ["-map", "1:v:0"]
    # else: no art

    # Audio encode settings: strict 320 CBR, 44.1kHz stereo
    cmd += [
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        "-minrate", "320k",
        "-maxrate", "320k",
        "-bufsize", "640k",
        "-ar", "44100",
        "-ac", "2",
        "-map_metadata", "0",
        "-write_id3v2", "1",
        "-id3v2_version", "3",
    ]

    # If we mapped art, ensure it's attached_pic and reasonable
    if mi.has_attached_pic or art_path is not None:
        # If external art is PNG, ffmpeg may write as png; Rekordbox is typically OK with JPG.
        # We re-encode to MJPEG and scale down to max 1000px on the long side.
        cmd += [
            "-c:v", "mjpeg",
            "-vf", "scale='if(gt(iw,ih),min(iw,1000),-2)':'if(gt(ih,iw),min(ih,1000),-2)'",
            "-disposition:v:0", "attached_pic",
        ]

    cmd += [str(dst)]

    vprint(f"[FFMPEG] {' '.join(cmd)}", verbose)
    p = run_cmd(cmd)
    if p.returncode != 0:
        return False, f"ffmpeg_failed:{p.stderr.strip()[:200]}"

    return True, "converted"


# -------------------------
# Dedupe (post-output)
# -------------------------

def audio_fingerprint_sha256(path: Path, seconds: int = 30) -> Optional[str]:
    """
    Decode first N seconds to PCM and hash it.
    Very robust for detecting same audio despite tag differences.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-v", "error",
        "-i", str(path),
        "-t", str(seconds),
        "-map", "0:a:0",
        "-f", "s16le",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "pipe:1"
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    if p.stdout is None:
        return None
    h = hashlib.sha256()
    while True:
        chunk = p.stdout.read(65536)
        if not chunk:
            break
        h.update(chunk)
    p.wait()
    if p.returncode != 0:
        return None
    return h.hexdigest()


# -------------------------
# Decision bookkeeping
# -------------------------

@dataclass
class DecisionRow:
    rb_name: str
    rb_artist: str
    rb_album: str
    rb_location: str

    source_path: str
    source_codec: str
    source_sr: str
    source_ch: str
    source_br: str
    source_duration: str

    classify_optimal: str
    classify_suboptimal: str
    classify_reasons: str
    hf_rms_db: str

    action: str
    out_path: str
    note: str


# -------------------------
# Main
# -------------------------

def main() -> int:
    ap = argparse.ArgumentParser()

    ap.add_argument("--in-root", required=True, help="Canonical library root (FLAC + everything).")
    ap.add_argument("--rekordbox-xml", required=True, help="Rekordbox XML path (DJ.xml).")
    ap.add_argument("--out-root", required=True, help="Output root (DJ_PREP).")

    ap.add_argument("--verbose", action="store_true", help="Print progress to stdout.")
    ap.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="Parallel ffprobe workers.")
    ap.add_argument("--prefer-folder-art", action="store_true", help="If no embedded art, embed cover.jpg/folder.jpg if present.")
    ap.add_argument("--hf-check", action="store_true", help="Heuristic fake-320 check using HF RMS (slow).")
    ap.add_argument("--hf-threshold", type=float, default=-50.0, help="HF RMS threshold in dB (more negative = more suspect).")

    ap.add_argument("--fallback-scan", action="store_true",
                    help="If XML paths are missing/broken, scan library for basenames to resolve.")
    ap.add_argument("--dedupe", action="store_true", help="Fingerprint outputs and move duplicates into DUPES folder.")
    ap.add_argument("--dedupe-seconds", type=int, default=30, help="Seconds of audio to hash for dedupe.")
    ap.add_argument("--skip-existing", action="store_true",
                    help="If output file already exists, skip actions (still reported).")

    args = ap.parse_args()

    in_root = Path(args.in_root)
    xml_path = Path(args.rekordbox_xml)
    out_root = Path(args.out_root)

    out_library = out_root / "LIBRARY"
    reports_root = out_root / "REPORTS" / f"run_{now_stamp()}"
    dupes_root = out_root / "DUPES" / reports_root.name

    reports_root.mkdir(parents=True, exist_ok=True)
    log_path = reports_root / "logs.txt"

    def log(msg: str) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        vprint(msg, args.verbose)

    # Phase 1: XML
    log(f"[XML] Parsing {xml_path}")
    rb_tracks = parse_rekordbox_xml(xml_path, args.verbose)

    # Phase 2: Resolve
    log("[RESOLVE] Resolving XML locations to actual files")
    resolved_pairs, unresolved_tracks = resolve_targets(
        rb_tracks=rb_tracks,
        in_root=in_root,
        verbose=args.verbose,
        do_fallback_scan=args.fallback_scan,
    )

    # If fallback scan yielded multiple candidates per track, we will probe candidates and choose best later.
    # To keep scale manageable, we dedupe probe list by path.
    probe_paths: List[Path] = []
    rb_for_path: Dict[Path, List[RBTrack]] = {}
    for rb, p in resolved_pairs:
        probe_paths.append(p)
        rb_for_path.setdefault(p, []).append(rb)
    probe_paths = sorted(set(probe_paths))

    log(f"[RESOLVE] Probe candidates: {len(probe_paths)} unique files")
    log(f"[RESOLVE] Unresolved tracks: {len(unresolved_tracks)}")

    # Write unresolved now
    unresolved_csv = reports_root / "unresolved.csv"
    with open(unresolved_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "artist", "album", "location"])
        for t in unresolved_tracks:
            w.writerow([t.name, t.artist, t.album, t.location or ""])
    log(f"[REPORT] Wrote {unresolved_csv}")

    # Phase 3: Probe (DJ only)
    log(f"[PROBE] Probing {len(probe_paths)} files with {args.max_workers} workers")
    t_probe0 = time.time()

    media_by_path: Dict[Path, MediaInfo] = {}
    probe_fail: List[Tuple[Path, str]] = []

    with ThreadPoolExecutor(max_workers=max(1, args.max_workers)) as ex:
        fut_map = {ex.submit(extract_media_info, p): p for p in probe_paths}
        done = 0
        total = len(probe_paths)

        for fut in as_completed(fut_map):
            p = fut_map[fut]
            done += 1
            if args.verbose and (done <= 20 or done % 100 == 0):
                log(f"[PROBE] {done}/{total} {p}")
            try:
                mi = fut.result()
                media_by_path[p] = mi
            except Exception as e:
                probe_fail.append((p, str(e)))
                log(f"[PROBE][FAIL] {p} :: {e}")

    log(f"[PROBE] Done in {time.time()-t_probe0:.2f}s. ok={len(media_by_path)} fail={len(probe_fail)}")

    # Phase 4: Choose best candidate per Rekordbox track key
    # Key: normalized(artist|title) + rounded duration if available
    def rb_track_key(rb: RBTrack) -> Tuple[str, str, Optional[int]]:
        a = normalize_key(rb.artist)
        t = normalize_key(rb.name)
        dur = int(round(rb.duration_sec)) if rb.duration_sec is not None else None
        return (a, t, dur)

    # Build candidate lists per RB track from resolved pairs
    candidates_for_rb: Dict[RBTrack, List[MediaInfo]] = {}
    for rb, p in resolved_pairs:
        mi = media_by_path.get(p)
        if mi is None:
            continue
        candidates_for_rb.setdefault(rb, []).append(mi)

    # Score candidates:
    # - Prefer lossless (for conversion)
    # - Prefer mp3 320-like
    # - Prefer closer duration to XML duration if present
    def candidate_score(rb: RBTrack, mi: MediaInfo) -> float:
        score = 0.0
        # lossless gets a huge boost as "best source" when mp3 needs regen
        is_lossless = (mi.path.suffix.lower() in LOSSLESS_EXTS) or (mi.codec == "alac")
        if is_lossless:
            score += 10000.0
        if mi.codec == "mp3":
            br = mi.bit_rate or mi.format_bit_rate or 0
            score += min(br / 1000.0, 400.0)
        sr = mi.sample_rate or 0
        if sr == 44100:
            score += 50.0

        if rb.duration_sec is not None and mi.duration:
            d = abs(mi.duration - rb.duration_sec)
            # penalize duration difference
            score -= min(d * 5.0, 500.0)

        return score

    # Phase 5: Decide action per RB track and execute
    decisions: List[DecisionRow] = []

    count_copy = 0
    count_convert = 0
    count_skip = 0
    count_reencode_lossy = 0

    log("[DECIDE] Classify and act (only regenerate if suboptimal)")

    for idx, rb in enumerate(rb_tracks, 1):
        # Skip unresolved
        if rb not in candidates_for_rb:
            continue

        # Choose best candidate for this RB track
        cands = candidates_for_rb[rb]
        cands_sorted = sorted(cands, key=lambda mi: candidate_score(rb, mi), reverse=True)

        # The first cand is "best available source"
        best = cands_sorted[0]

        # classify best
        cls = classify_for_rekordbox(best, args.hf_check, args.hf_threshold)

        out_path = build_output_path(out_library, rb, best)

        rb_loc = rb.location or ""
        src_path = str(best.path)

        if args.skip_existing and out_path.exists():
            decisions.append(
                DecisionRow(
                    rb_name=rb.name, rb_artist=rb.artist, rb_album=rb.album, rb_location=rb_loc,
                    source_path=src_path, source_codec=best.codec,
                    source_sr=str(best.sample_rate or ""), source_ch=str(best.channels or ""),
                    source_br=str(best.bit_rate or best.format_bit_rate or ""), source_duration=f"{best.duration:.3f}",
                    classify_optimal=str(cls.is_optimal_mp3), classify_suboptimal=str(cls.is_suboptimal),
                    classify_reasons=";".join(cls.reasons), hf_rms_db="" if cls.hf_rms_db is None else f"{cls.hf_rms_db:.2f}",
                    action="skip_existing", out_path=str(out_path), note="output_exists",
                )
            )
            count_skip += 1
            continue

        # If best is an optimal MP3 -> copy as-is
        if cls.is_mp3 and cls.is_optimal_mp3:
            copy_file(best.path, out_path, args.verbose)
            decisions.append(
                DecisionRow(
                    rb_name=rb.name, rb_artist=rb.artist, rb_album=rb.album, rb_location=rb_loc,
                    source_path=src_path, source_codec=best.codec,
                    source_sr=str(best.sample_rate or ""), source_ch=str(best.channels or ""),
                    source_br=str(best.bit_rate or best.format_bit_rate or ""), source_duration=f"{best.duration:.3f}",
                    classify_optimal=str(cls.is_optimal_mp3), classify_suboptimal=str(cls.is_suboptimal),
                    classify_reasons=";".join(cls.reasons), hf_rms_db="" if cls.hf_rms_db is None else f"{cls.hf_rms_db:.2f}",
                    action="copy_optimal_mp3", out_path=str(out_path), note="",
                )
            )
            count_copy += 1
            continue

        # Otherwise: suboptimal => try to find a lossless candidate among cands for true upgrade
        lossless_cands = [mi for mi in cands_sorted if (mi.path.suffix.lower() in LOSSLESS_EXTS) or (mi.codec == "alac")]

        if lossless_cands:
            src_for_convert = lossless_cands[0].path
            ok, note = convert_to_mp3_320(
                src_for_convert,
                out_path,
                prefer_folder_art=args.prefer_folder_art,
                verbose=args.verbose,
            )
            decisions.append(
                DecisionRow(
                    rb_name=rb.name, rb_artist=rb.artist, rb_album=rb.album, rb_location=rb_loc,
                    source_path=str(src_for_convert), source_codec=lossless_cands[0].codec,
                    source_sr=str(lossless_cands[0].sample_rate or ""), source_ch=str(lossless_cands[0].channels or ""),
                    source_br=str(lossless_cands[0].bit_rate or lossless_cands[0].format_bit_rate or ""),
                    source_duration=f"{lossless_cands[0].duration:.3f}",
                    classify_optimal="False", classify_suboptimal="True",
                    classify_reasons="upgrade_from_lossless", hf_rms_db="",
                    action="convert_from_lossless" if ok else "convert_failed",
                    out_path=str(out_path),
                    note=note,
                )
            )
            if ok:
                count_convert += 1
            else:
                count_skip += 1
            continue

        # No lossless candidate exists; we re-encode the best mp3 for compatibility (still suboptimal source)
        ok, note = convert_to_mp3_320(
            best.path,
            out_path,
            prefer_folder_art=args.prefer_folder_art,
            verbose=args.verbose,
        )
        decisions.append(
            DecisionRow(
                rb_name=rb.name, rb_artist=rb.artist, rb_album=rb.album, rb_location=rb_loc,
                source_path=src_path, source_codec=best.codec,
                source_sr=str(best.sample_rate or ""), source_ch=str(best.channels or ""),
                source_br=str(best.bit_rate or best.format_bit_rate or ""), source_duration=f"{best.duration:.3f}",
                classify_optimal=str(cls.is_optimal_mp3), classify_suboptimal=str(cls.is_suboptimal),
                classify_reasons=";".join(cls.reasons), hf_rms_db="" if cls.hf_rms_db is None else f"{cls.hf_rms_db:.2f}",
                action="reencode_from_lossy" if ok else "reencode_failed",
                out_path=str(out_path),
                note=note,
            )
        )
        if ok:
            count_reencode_lossy += 1
        else:
            count_skip += 1

        if args.verbose and idx % 50 == 0:
            log(f"[DECIDE] processed {idx}/{len(rb_tracks)}")

    # Phase 6: Reports
    decisions_csv = reports_root / "decisions.csv"
    with open(decisions_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(DecisionRow.__annotations__.keys()))
        for d in decisions:
            w.writerow([
                d.rb_name, d.rb_artist, d.rb_album, d.rb_location,
                d.source_path, d.source_codec, d.source_sr, d.source_ch, d.source_br, d.source_duration,
                d.classify_optimal, d.classify_suboptimal, d.classify_reasons, d.hf_rms_db,
                d.action, d.out_path, d.note
            ])
    log(f"[REPORT] Wrote {decisions_csv}")

    summary = {
        "xml": str(xml_path),
        "in_root": str(in_root),
        "out_root": str(out_root),
        "resolved_candidates": len(resolved_pairs),
        "resolved_unique_files_probed": len(probe_paths),
        "unresolved_tracks": len(unresolved_tracks),
        "decisions": len(decisions),
        "actions": {
            "copy_optimal_mp3": count_copy,
            "convert_from_lossless": count_convert,
            "reencode_from_lossy": count_reencode_lossy,
            "skipped_or_failed": count_skip,
        },
        "hf_check": bool(args.hf_check),
        "hf_threshold_db": args.hf_threshold,
        "timestamp": reports_root.name,
    }
    summary_path = reports_root / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log(f"[REPORT] Wrote {summary_path}")

    # Phase 7: Dedupe
    duplicates_csv = reports_root / "duplicates.csv"
    if args.dedupe:
        log(f"[DEDUPE] Fingerprinting outputs (seconds={args.dedupe_seconds})")

        out_files = sorted(out_library.rglob("*.mp3"))
        fp_map: Dict[str, Path] = {}
        dup_rows: List[Tuple[str, str, str]] = []

        dupes_root.mkdir(parents=True, exist_ok=True)

        for i, mp3 in enumerate(out_files, 1):
            if args.verbose and (i <= 20 or i % 200 == 0):
                log(f"[DEDUPE] {i}/{len(out_files)} {mp3}")
            fp = audio_fingerprint_sha256(mp3, seconds=args.dedupe_seconds)
            if fp is None:
                dup_rows.append(("fp_failed", str(mp3), ""))
                continue
            if fp in fp_map:
                original = fp_map[fp]
                # Move duplicate to DUPES preserving relative path
                rel = mp3.relative_to(out_library)
                target = dupes_root / rel
                ensure_parent(target)
                shutil.move(str(mp3), str(target))
                dup_rows.append((fp, str(original), str(target)))
            else:
                fp_map[fp] = mp3

        with open(duplicates_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fingerprint", "kept", "moved_duplicate_to"])
            w.writerows(dup_rows)
        log(f"[REPORT] Wrote {duplicates_csv}")
    else:
        # Still write an empty duplicates report for consistency
        with open(duplicates_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["fingerprint", "kept", "moved_duplicate_to"])
        log(f"[REPORT] Wrote {duplicates_csv} (dedupe disabled)")

    # Phase 8: Print Codex prompt (so you can paste into Codex and integrate into tagslut)
    codex_prompt = f"""
You are integrating a DJ prep step into the tagslut workflow.

Goal:
- Build Rekordbox-ready MP3 library from a Rekordbox DJ.xml, using the canonical library as sources.
- Only regenerate MP3 when the existing MP3 is suboptimal.
- Convert lossless sources to MP3 320 CBR 44.1kHz stereo, ID3v2.3, and embed cover art if possible.
- Dedupe output files by audio fingerprint and move duplicates into a DUPES folder.

Existing script:
{Path(__file__).resolve()}

Expected CLI usage:
python3 {Path(__file__).name} \\
  --in-root "{in_root}" \\
  --rekordbox-xml "{xml_path}" \\
  --out-root "{out_root}" \\
  --prefer-folder-art \\
  --skip-existing \\
  --dedupe \\
  --verbose

First check:
- Before running, check if the output root "{out_root}" already contains a prior run folder under REPORTS.
- If it exists, do NOT overwrite. Create a new run folder.
- Ensure no destructive actions occur by default.

Integrate:
- Add a tagslut CLI wrapper command (e.g. tagslut dj prep) that calls this script.
- Wire DB provenance logging (db path: /Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-08 or current epoch) into the run summary.
- Store run artifacts under the epoch folder as well (optional mirror), but keep the output audio under "{out_root}/LIBRARY".

Constraints:
- No broad full-library ffprobe scan. Only probe DJ targets (from XML).
- Maintain verbose progress.
"""
    codex_path = reports_root / "codex_prompt.txt"
    with open(codex_path, "w", encoding="utf-8") as f:
        f.write(codex_prompt.strip() + "\n")
    log(f"[REPORT] Wrote {codex_path}")

    log("[DONE] Completed DJ prep run.")
    log(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
