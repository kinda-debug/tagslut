#!/usr/bin/env python3
"""
useful_scan.py — sweep a home directory for "useful" media/library artefacts.

Targets (by category):
  - audio           : .flac .wav .aiff .aif .alac .m4a .mp3 .ogg .opus .wma .wv .ape .dsf .dff .mka
  - playlists       : .m3u .m3u8 .pls .cue .log (ripping logs)
  - artwork         : cover/folder/front/back.* (jpg/png/webp) next to audio
  - itunes_music    : Music.app / iTunes libraries (Music Library.musiclibrary, iTunes*.itl, iTunes*Library.xml)
  - roon            : Roon / RoonServer / RAATServer folders & databases
  - dj              : Serato, Traktor, Rekordbox libraries and DBs
  - recovery        : R-Studio scan projects (*.scn, *.scn2), rescue logs
  - ios_backups     : MobileSync/Backup (device backups)
  - whatsapp        : WhatsApp/iCloud artifacts under Mobile Documents (if --include-icloud)
  - archives_media  : archives whose names look audio-related (.zip/.7z/.rar with flac/wav in name)

Skips heavy/noisy locations by default:
  ~/Library/Caches, ~/Library/Logs, ~/.Trash, .Spotlight-V100, node_modules, .git, Photos*.photoslibrary, etc.

Outputs (under ./useful_scan_out_<timestamp> by default):
  - useful_files.csv     : one row per hit (category, path, size, mtime, hash?)
  - per_category.csv     : totals by category
  - top_large.csv        : top N largest hits across categories
  - SUMMARY.txt          : human summary + next steps
  - move_plan.sh         : OPTIONAL reviewable plan to move selected categories to a staging folder

Notes
  - No deletions. The optional move plan only prepares a reviewed move to a staging dir.
  - Add --hash to compute SHA-1 for hash-join with later audio dedupe scans.
"""

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

AUDIO_EXTS = {
    ".flac", ".wav", ".aiff", ".aif", ".alac", ".m4a", ".mp3", ".ogg", ".opus", ".wma", ".wv", ".ape", ".dsf", ".dff", ".mka"
}
PLAYLIST_EXTS = {".m3u", ".m3u8", ".pls", ".cue", ".log"}
ARTWORK_HINTS = ("cover", "folder", "front", "back", "artwork", "scan")
ARTWORK_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff"}

ARCHIVE_EXTS = {".zip", ".7z", ".rar"}

DEFAULT_SKIP_DIR_BASENAMES = {
    ".git", ".Trash", ".Trashes", ".Spotlight-V100", ".fseventsd", "__MACOSX",
    "node_modules", "Caches", "Cache", "temp", "tmp"
}
DEFAULT_SKIP_DIR_PATTERNS = [
    re.compile(r"/Library/Caches(/|$)"),
    re.compile(r"/Library/Logs(/|$)"),
    re.compile(r"\.photoslibrary(/|$)", re.IGNORECASE),
    re.compile(r"/Application Support/Dropbox(/|$)"),
    re.compile(r"/Application Support/Google/Drive(/|$)"),
    re.compile(r"/Group Containers/.+/(Library|Caches)(/|$)"),
]
ICLOUD_MOBILE_DOCS_FRAGMENT = "Library/Mobile Documents"

@dataclass
class Hit:
    category: str
    path: Path
    size: int
    mtime: float
    sha1: Optional[str] = None

def human_bytes(n: int) -> str:
    units = ["B","KB","MB","GB","TB","PB"]
    i = 0
    x = float(n)
    while i < len(units)-1 and x >= 1024:
        x /= 1024.0
        i += 1
    return f"{x:.2f} {units[i]}"

def sha1_file(p: Path, bufsize: int = 1024*1024) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        while True:
            b = f.read(bufsize)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def should_skip_dir(dirpath: str) -> bool:
    bn = os.path.basename(dirpath)
    if bn in DEFAULT_SKIP_DIR_BASENAMES:
        return True
    sp = dirpath
    for pat in DEFAULT_SKIP_DIR_PATTERNS:
        if pat.search(sp):
            return True
    return False

def walk_files(root: Path, follow_symlinks: bool = False) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # Prune noisy dirs
        pruned = []
        for d in list(dirnames):
            full = os.path.join(dirpath, d)
            if should_skip_dir(full):
                pruned.append(d)
        for d in pruned:
            dirnames.remove(d)
        for fn in filenames:
            if fn.startswith("._"):
                continue
            yield Path(dirpath) / fn

def looks_like_artwork(fn: str) -> bool:
    name, ext = os.path.splitext(os.path.basename(fn))
    if ext.lower() not in ARTWORK_EXTS:
        return False
    lname = name.lower()
    return any(h in lname for h in ARTWORK_HINTS)

def find_category(p: Path, include_icloud: bool) -> Optional[str]:
    s = str(p)
    ext = p.suffix.lower()

    # Audio
    if ext in AUDIO_EXTS:
        return "audio"

    # Playlists / ripping logs
    if ext in PLAYLIST_EXTS:
        if ext == ".log":
            return "playlists"  # keep with playlists for convenience
        return "playlists"

    # Artwork near audio
    if ext in ARTWORK_EXTS and looks_like_artwork(s):
        return "artwork"

    # iTunes / Music.app libraries
    low = s.lower()
    if low.endswith("music library.musiclibrary") or low.endswith(".itl") or "itunes" in low and (low.endswith(".itl") or low.endswith(".xml")):
        return "itunes_music"
    if "/Music/" in s and (s.endswith(".musiclibrary") or "Music Library.musiclibrary" in s):
        return "itunes_music"

    # Roon
    if any(seg in s for seg in ("/RoonServer", "/RAATServer", "/Roon/")):
        return "roon"

    # DJ libraries
    if any(seg in s for seg in ("/Serato", "/Traktor", "/Native Instruments/Traktor", "/rekordbox", "/Pioneer/rekordbox")):
        return "dj"

    # R-Studio scans / recovery
    if ext in {".scn", ".scn2"}:
        return "recovery"
    if "R-Studio" in s or "RStudio" in s:
        if ext in {".txt", ".log", ".csv", ".xml"}:
            return "recovery"

    # iOS backups
    if "/Library/Application Support/MobileSync/Backup" in s:
        return "ios_backups"

    # WhatsApp / iCloud Documents
    if include_icloud and ICLOUD_MOBILE_DOCS_FRAGMENT in s and "whatsapp" in s.lower():
        return "whatsapp"

    # Archives that look media related (name contains flac/wav)
    if ext in ARCHIVE_EXTS:
        base = p.name.lower()
        if any(tag in base for tag in ("flac", "wav", "aiff", "alac")):
            return "archives_media"

    return None

def scan(root: Path, categories: Set[str], include_icloud: bool, compute_hash: bool) -> List[Hit]:
    hits: List[Hit] = []
    total = 0
    t0 = time.time()
    for i, p in enumerate(walk_files(root)):
        try:
            cat = find_category(p, include_icloud)
            if cat is None or (categories and cat not in categories):
                continue
            st = p.stat()
            sha1 = sha1_file(p) if compute_hash and cat in {"audio", "playlists"} and st.st_size > 0 else None
            hits.append(Hit(category=cat, path=p, size=st.st_size, mtime=st.st_mtime, sha1=sha1))
            total += 1
            if total % 1000 == 0:
                elapsed = time.time() - t0
                print(f"... {total} hits so far ({elapsed:.1f}s)", file=sys.stderr)
        except (PermissionError, FileNotFoundError):
            continue
    return hits

def write_csv(path: Path, rows: List[Dict[str, object]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main():
    ap = argparse.ArgumentParser(description="Scan a home dir for useful media/library artefacts.")
    ap.add_argument("--root", default="/Users/georgeskhawam", help="Root directory to scan.")
    ap.add_argument("--include-icloud", action="store_true", help="Also scan iCloud Mobile Documents subtrees for WhatsApp/etc.")
    ap.add_argument("--categories", nargs="*", default=[],
                    help="Limit to specific categories: audio playlists artwork itunes_music roon dj recovery ios_backups whatsapp archives_media")
    ap.add_argument("--hash", action="store_true", help="Compute SHA-1 for audio/playlist files for later dedupe joins.")
    ap.add_argument("--save-dir", default="", help="Output directory (default ./useful_scan_out_<timestamp>)")
    ap.add_argument("--write-plan", action="store_true", help="Write move_plan.sh to stage selected categories to ./_staging.")
    ap.add_argument("--stage-categories", nargs="*", default=[],
                    help="Categories to include in move_plan (default: same as --categories or all found if --categories omitted).")
    ap.add_argument("--top-n", type=int, default=50, help="How many largest hits to include in top_large.csv")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    if not root.exists():
        print(f"ERROR: root not found: {root}", file=sys.stderr)
        sys.exit(2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(args.save_dir) if args.save_dir else Path(f"./useful_scan_out_{ts}")
    outdir.mkdir(parents=True, exist_ok=True)

    want_cats = set(args.categories)
    if want_cats:
        valid = {"audio","playlists","artwork","itunes_music","roon","dj","recovery","ios_backups","whatsapp","archives_media"}
        bad = want_cats - valid
        if bad:
            print(f"ERROR: unknown categories: {', '.join(sorted(bad))}", file=sys.stderr)
            sys.exit(2)

    print(f"[i] Scanning: {root}")
    print(f"[i] Include iCloud Mobile Documents: {'YES' if args.include_icloud else 'NO'}")
    print(f"[i] Categories filter: {', '.join(sorted(want_cats)) if want_cats else '(all)'}")
    print(f"[i] Hash audio/playlists: {'YES' if args.hash else 'NO'}")
    print(f"[i] Output dir: {outdir}")

    hits = scan(root, want_cats, args.include_icloud, args.hash)
    if not hits:
        print("No hits. Adjust filters and retry.", file=sys.stderr)
        return

    # Write useful_files.csv
    rows = []
    for h in hits:
        rows.append({
            "category": h.category,
            "path": str(h.path),
            "size_bytes": h.size,
            "size_h": human_bytes(h.size),
            "mtime_iso": datetime.fromtimestamp(h.mtime).isoformat(timespec="seconds"),
            "sha1": h.sha1 or "",
        })
    rows.sort(key=lambda r: (r["category"], r["path"]))
    files_csv = outdir / "useful_files.csv"
    write_csv(files_csv, rows, ["category","path","size_bytes","size_h","mtime_iso","sha1"])
    print(f"[+] Wrote {files_csv}")

    # Per-category summary
    cat_totals: Dict[str, Tuple[int,int]] = {}
    for h in hits:
        cnt, sz = cat_totals.get(h.category, (0,0))
        cat_totals[h.category] = (cnt+1, sz+h.size)
    percat_rows = []
    for cat, (cnt, sz) in sorted(cat_totals.items(), key=lambda kv: (-kv[1][1], kv[0])):
        percat_rows.append({"category": cat, "count": cnt, "total_bytes": sz, "total_h": human_bytes(sz)})
    percat_csv = outdir / "per_category.csv"
    write_csv(percat_csv, percat_rows, ["category","count","total_bytes","total_h"])
    print(f"[+] Wrote {percat_csv}")

    # Top N largest
    topn = sorted(hits, key=lambda h: h.size, reverse=True)[:max(1, args.top_n)]
    top_rows = [{
        "category": h.category,
        "path": str(h.path),
        "size_bytes": h.size,
        "size_h": human_bytes(h.size),
        "mtime_iso": datetime.fromtimestamp(h.mtime).isoformat(timespec="seconds"),
    } for h in topn]
    top_csv = outdir / "top_large.csv"
    write_csv(top_csv, top_rows, ["category","path","size_bytes","size_h","mtime_iso"])
    print(f"[+] Wrote {top_csv}")

    # SUMMARY.txt
    grand_bytes = sum(h.size for h in hits)
    summary_lines = []
    summary_lines.append(f"Root: {root}")
    summary_lines.append(f"Total hits: {len(hits)}  Total size: {human_bytes(grand_bytes)}")
    summary_lines.append("")
    summary_lines.append("Per-category:")
    for r in percat_rows:
        summary_lines.append(f"  - {r['category']:<14} : {r['count']:>7} files, {r['total_h']:>10}")
    summary_lines.append("")
    summary_lines.append("Top largest files (see top_large.csv for full paths).")
    summary_lines.append("")
    summary_lines.append("Next steps:")
    summary_lines.append("  1) Skim per_category.csv to decide what to stage or archive.")
    summary_lines.append("  2) If preparing a relocation: use --write-plan to generate move_plan.sh for selected categories.")
    summary_lines.append("  3) After review, run the plan and verify in staging; do not delete originals until validated.")
    (outdir / "SUMMARY.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"[+] Wrote {outdir/'SUMMARY.txt'}")

    # Optional move plan
    if args.write_plan:
        move_cats = set(args.stage_categories) if args.stage_categories else (want_cats if want_cats else set(cat_totals.keys()))
        sh = outdir / "move_plan.sh"
        staging = outdir / "_staging"
        lines = []
        lines.append("#!/usr/bin/env bash")
        lines.append("set -euo pipefail")
        lines.append(f'STAGE="{staging}"')
        lines.append('mkdir -p "$STAGE"')
        lines.append("")
        lines.append("# Selected categories to stage:")
        lines.append(f"#   {', '.join(sorted(move_cats))}")
        for h in hits:
            if h.category not in move_cats:
                continue
            rel = os.path.relpath(str(h.path), start=str(root))
            dest = staging / h.category / rel
            dest_dir = os.path.dirname(str(dest))
            # Use mv -n to avoid overwrites; adjust to cp -n if you prefer copy
            lines.append(f'mkdir -p "{dest_dir}"')
            lines.append(f'mv -n "{h.path}" "{dest}" || true')
        sh.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(sh, 0o755)
        print(f"[+] Wrote {sh}\n    Review before running. It moves files into {staging} by category.")

if __name__ == "__main__":
    main()
