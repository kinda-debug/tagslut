#!/usr/bin/env python3
import os
import shutil
from pathlib import Path
from mutagen.flac import FLAC

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

SRC_LIST = Path("artifacts/reports/healthy_flacs.txt")
DEST_ROOT = Path("/Volumes/dotad/NEW_LIBRARY_CLEAN")
LOG = Path("artifacts/reports/metadata_rebuild_log.txt")
MANIFEST = Path("artifacts/reports/metadata_rebuild_manifest.txt")

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------

def safe_str(s: str) -> str:
    """Safe filesystem string."""
    if not s:
        return "Unknown"
    return s.replace(":", "꞉").replace("/", "_")

def parse_int(v, default=0):
    """Extract integer from tag values like '3/10' or ['03']."""
    try:
        if isinstance(v, list):
            v = v[0]
        if isinstance(v, str):
            v = v.split("/")[0]
        return int(v)
    except Exception:
        return default

def get_year(tags):
    """Extract 4-digit year or return 'XXXX'."""
    for key in ("date", "originalyear", "originaldate"):
        if key in tags:
            val = tags[key][0]
            if len(val) >= 4 and val[:4].isdigit():
                return val[:4]
    return "XXXX"

def build_target_path(tags):
    """
    Builds:

    Artist/
        (YEAR) Album/
            Artist - (YEAR) Album - [Disc prefix]Track. Title.flac
    """

    artist = safe_str(tags.get("albumartist", tags.get("artist", ["Unknown Artist"]))[0])
    album = safe_str(tags.get("album", ["Unknown Album"])[0])
    title = safe_str(tags.get("title", ["Unknown Title"])[0])
    year = get_year(tags)

    disc = parse_int(tags.get("discnumber"), 1)
    total_discs = parse_int(tags.get("totaldiscs"), 1)
    track = parse_int(tags.get("tracknumber"), 0)

    folder_artist = artist
    folder_album = f"({year}) {album}"

    if total_discs > 1:
        track_component = f"{disc:02d}-{track:02d}"
    else:
        track_component = f"{track:02d}"

    filename = f"{artist} - ({year}) {album} - {track_component}. {title}.flac"

    return Path(folder_artist) / folder_album / filename

def ensure_unique(dest: Path) -> Path:
    """If a file already exists, append '(duplicate N)' before extension."""
    if not dest.exists():
        return dest

    base = dest.with_suffix("")
    ext = dest.suffix

    n = 1
    while True:
        candidate = Path(str(base) + f" (duplicate {n})" + ext)
        if not candidate.exists():
            return candidate
        n += 1

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)

    count_ok = 0
    count_missing = 0
    count_read_err = 0
    count_copied = 0

    with LOG.open("w", encoding="utf8") as log, MANIFEST.open("w", encoding="utf8") as mf:
        if not SRC_LIST.exists():
            print("ERROR: healthy_flacs.txt not found.")
            return

        for line in SRC_LIST.read_text().splitlines():
            src = Path(line.strip())
            if not src.exists():
                log.write(f"MISSING: {src}\n")
                count_missing += 1
                continue

            # Load metadata
            try:
                flac = FLAC(src)
            except Exception as e:
                log.write(f"READ_ERROR: {src} | {e}\n")
                count_read_err += 1
                continue

            # Build target path
            target_rel = build_target_path(flac)
            dest_file = ensure_unique(DEST_ROOT / target_rel)

            # Make sure directory exists
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy
            try:
                shutil.copy2(src, dest_file)
                mf.write(f"{src} -> {dest_file}\n")
                count_copied += 1
            except Exception as e:
                log.write(f"COPY_FAIL: {src} -> {dest_file} | {e}\n")

            count_ok += 1

    print("Metadata rebuild completed.")
    print("Source list:", SRC_LIST)
    print("Destination:", DEST_ROOT)
    print("Log:", LOG)
    print("Manifest:", MANIFEST)
    print("---- Summary ----")
    print("Valid entries:", count_ok)
    print("Missing:", count_missing)
    print("Read errors:", count_read_err)
    print("Copied:", count_copied)

if __name__ == "__main__":
    main()
