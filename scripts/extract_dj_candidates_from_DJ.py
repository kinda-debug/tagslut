#!/usr/bin/env python3
"""
extract_dj_candidates_from_DJ.py

Goal:
- Expand DJ_LIBRARY_MP3 by finding structurally compatible tracks under /Volumes/MUSIC/DJ
- Use BPM envelope + explicit classical/composer blacklist to avoid "Bon Iver / Bach / symphonies" style pollution.
- Output a candidate audition playlist + report.

Defaults:
- DJ source root: /Volumes/MUSIC/DJ
- BPM band: 110..132 (centered around median 122)
- Output folder: /Volumes/MUSIC/DJ_LIBRARY_MP3/_candidates

Outputs:
- candidates_bpm110-132.m3u8
- candidates_report.csv

Requirements:
- ffprobe available on PATH (comes with ffmpeg)

Usage:
  python3 scripts/extract_dj_candidates_from_DJ.py
  python3 scripts/extract_dj_candidates_from_DJ.py --min-bpm 112 --max-bpm 130
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a"}

# Explicit classical / orchestral / academic music blacklist keywords.
# This is intentionally "dumb and strict": if it matches, we exclude.
CLASSICAL_KEYWORDS = [
    "classical", "symphony", "symphonies", "orchestra", "orchestral",
    "concerto", "sonata", "cantata", "requiem", "mass", "opus", "op.",
    "philarmonic", "philharmonic", "chamber", "string quartet", "quartet",
    "piano trio", "violin", "cello", "harpsichord", "baroque", "romantic era",
    "composer", "conducted by", "conductor",
    "bach", "j.s. bach", "johann sebastian bach",
    "beethoven", "mozart", "haydn", "schubert", "schumann", "chopin",
    "tchaikovsky", "rachmaninoff", "debussy", "ravel", "mahler", "brahms",
    "handel", "vivaldi", "wagner", "dvorak", "prokofiev", "shostakovich",
    "liszt", "satie", "stravinsky",
]

# Also blacklist obvious library folders you might have under /Volumes/MUSIC/DJ
# (adjust/add as needed)
CLASSICAL_PATH_HINTS = [
    "/classical/",
    "/symphon",
    "/orchestra",
    "/bach",
    "/schubert",
]

# Normalize & compile regex for keyword matching
def _compile_keyword_regex(keywords: List[str]) -> re.Pattern:
    escaped = [re.escape(k.strip().lower()) for k in keywords if k.strip()]
    # match as substring; for short tokens like "op." it's still ok in context
    pat = "(" + "|".join(escaped) + ")"
    return re.compile(pat, re.IGNORECASE)

CLASSICAL_RE = _compile_keyword_regex(CLASSICAL_KEYWORDS)

@dataclass
class Candidate:
    path: Path
    bpm: float
    reason: str
    tags: Dict[str, str]


def die(msg: str, code: int = 2) -> None:
    raise SystemExit(msg)


def run_ffprobe_tags(path: Path) -> Dict[str, str]:
    """
    Extract selected tags via ffprobe. Returns lowercased keys.
    """
    # We ask for a few tag fields. Missing fields simply won't appear.
    # format_tags is easiest to scrape in flat form.
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format_tags",
        "-of", "default=nw=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd).decode("utf-8", errors="replace")
    except Exception:
        return {}

    tags: Dict[str, str] = {}
    for line in out.splitlines():
        # Example: TAG:BPM=122
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        # Accept lines like TAG:artist
        if k.lower().startswith("tag:"):
            k = k[4:]
        tags[k.lower()] = v
    return tags


def parse_bpm(tags: Dict[str, str]) -> Optional[float]:
    """
    Try multiple common BPM tag keys. Return float or None.
    """
    for key in ("bpm", "tbpm", "tempo"):
        if key in tags:
            raw = tags[key].strip()
            if not raw:
                continue
            try:
                return float(raw)
            except Exception:
                # Sometimes BPM is like "122.00" or "122,0"
                raw2 = raw.replace(",", ".")
                try:
                    return float(raw2)
                except Exception:
                    continue
    return None


def looks_classical(path: Path, tags: Dict[str, str]) -> Tuple[bool, str]:
    """
    Returns (is_classical, matched_reason).
    Checks:
      - path hints
      - keywords across path + selected tag fields (artist/album/title/genre/composer)
    """
    p = path.as_posix().lower()

    for hint in CLASSICAL_PATH_HINTS:
        if hint in p:
            return True, f"path_hint:{hint}"

    # Build a text blob for matching
    fields = []
    for k in ("artist", "album", "title", "genre", "composer", "album_artist", "albumartist"):
        if k in tags and tags[k].strip():
            fields.append(tags[k].strip())
    blob = (p + "\n" + "\n".join(fields)).lower()

    m = CLASSICAL_RE.search(blob)
    if m:
        return True, f"keyword:{m.group(0)}"

    return False, ""


def iter_audio_files(root: Path) -> List[Path]:
    out: List[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in AUDIO_EXTS:
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/Volumes/MUSIC/DJ", help="Source root to scan")
    ap.add_argument("--min-bpm", type=float, default=110.0)
    ap.add_argument("--max-bpm", type=float, default=132.0)
    ap.add_argument("--out-root", default="/Volumes/MUSIC/DJ_LIBRARY_MP3/_candidates",
                    help="Folder where outputs are written")
    ap.add_argument("--limit", type=int, default=0, help="Optional cap on number of candidates (0=all)")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        die(f"Root not found: {root}")

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    min_bpm = float(args.min_bpm)
    max_bpm = float(args.max_bpm)
    if min_bpm <= 0 or max_bpm <= 0 or max_bpm < min_bpm:
        die("Invalid BPM range")

    files = iter_audio_files(root)
    if not files:
        die(f"No audio files found under: {root}")

    candidates: List[Candidate] = []
    skipped_no_bpm = 0
    skipped_classical = 0
    skipped_out_of_range = 0

    for p in files:
        tags = run_ffprobe_tags(p)
        bpm = parse_bpm(tags)
        if bpm is None:
            skipped_no_bpm += 1
            continue

        # Strict classical exclusion
        is_class, why = looks_classical(p, tags)
        if is_class:
            skipped_classical += 1
            continue

        if not (min_bpm <= bpm <= max_bpm):
            skipped_out_of_range += 1
            continue

        candidates.append(Candidate(path=p, bpm=bpm, reason="bpm_band", tags=tags))

    # Sort by BPM (then path)
    candidates.sort(key=lambda c: (c.bpm, c.path.as_posix().lower()))

    if args.limit and args.limit > 0:
        candidates = candidates[: args.limit]

    # Write M3U8 with absolute paths (Rekordbox-friendly)
    m3u_name = f"candidates_bpm{int(min_bpm)}-{int(max_bpm)}.m3u8"
    m3u_path = out_root / m3u_name
    with m3u_path.open("w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for c in candidates:
            f.write(c.path.as_posix() + "\n")

    # Write report CSV
    csv_path = out_root / "candidates_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["bpm", "path", "artist", "title", "album", "genre", "composer"])
        for c in candidates:
            t = c.tags
            w.writerow([
                f"{c.bpm:.2f}",
                c.path.as_posix(),
                t.get("artist", ""),
                t.get("title", ""),
                t.get("album", ""),
                t.get("genre", ""),
                t.get("composer", ""),
            ])

    print(f"Scanned root: {root}")
    print(f"Audio files found: {len(files)}")
    print(f"Candidates (BPM {min_bpm}-{max_bpm}, classical excluded): {len(candidates)}")
    print(f"Skipped: no_bpm={skipped_no_bpm}, classical={skipped_classical}, out_of_range={skipped_out_of_range}")
    print(f"Wrote M3U8: {m3u_path}")
    print(f"Wrote report: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

