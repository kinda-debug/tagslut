#!/usr/bin/env python3
import os
import re
import sys
import unicodedata
from pathlib import Path

FLAC_DIR = Path("/Users/georgeskhawam/Music/yesflac")
MP3_DIR  = Path("/Users/georgeskhawam/Music/yesmp3")

# Set to True to actually delete
DO_DELETE = True

def normalize_name(p: Path) -> str:
    """Normalize filename for matching: unicode fold, lowercase, strip ext, reduce punctuation/whitespace."""
    name = p.name
    # strip extension
    name = re.sub(r"\.[^.]+$", "", name)

    # Unicode normalize + remove diacritics
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))

    # lowercase
    name = name.lower()

    # replace non-alnum with space
    name = re.sub(r"[^a-z0-9]+", " ", name)

    # collapse spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name

def iter_files(root: Path, exts: tuple[str, ...]):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p

def main():
    if not FLAC_DIR.exists():
        print(f"FLAC_DIR not found: {FLAC_DIR}", file=sys.stderr)
        sys.exit(1)
    if not MP3_DIR.exists():
        print(f"MP3_DIR not found: {MP3_DIR}", file=sys.stderr)
        sys.exit(1)

    mp3_norm = {}
    for mp3 in iter_files(MP3_DIR, (".mp3",)):
        n = normalize_name(mp3)
        # keep first seen path for reference
        mp3_norm.setdefault(n, mp3)

    flacs = list(iter_files(FLAC_DIR, (".flac",)))
    total_mp3 = len(list(iter_files(MP3_DIR, (".mp3",))))
    total_flac = len(flacs)

    matches = []
    nonmatches = []

    for flac in flacs:
        n = normalize_name(flac)
        if n in mp3_norm:
            matches.append((flac, mp3_norm[n], n))
        else:
            nonmatches.append((flac, n))

    print(f"MP3 files:  {total_mp3}")
    print(f"FLAC files: {total_flac}")
    print(f"Matches:    {len(matches)}")
    print(f"No match:   {len(nonmatches)}")
    print()

    if not matches:
        print("No matches found. Showing 25 sample normalized names from each side:\n")
        print("Sample MP3 normalized:")
        for i, k in enumerate(sorted(mp3_norm.keys())[:25], 1):
            print(f"{i:02d}. {k}")
        print("\nSample FLAC normalized:")
        for i, (flac, n) in enumerate(nonmatches[:25], 1):
            print(f"{i:02d}. {n}   <- {flac.name}")
        sys.exit(0)

    if not DO_DELETE:
        print("DRY RUN — FLAC files that WOULD be deleted (showing up to 200):\n")
        for i, (flac, mp3, n) in enumerate(matches[:200], 1):
            print(f"{i:04d}. {flac}   [mp3: {mp3.name}]")
        print("\nTo actually delete, edit DO_DELETE=True in the script and rerun.")
        sys.exit(0)

    # Delete
    deleted = 0
    for flac, mp3, n in matches:
        try:
            flac.unlink()
            deleted += 1
        except Exception as e:
            print(f"FAILED to delete: {flac} ({e})", file=sys.stderr)

    print(f"\nDeleted {deleted} FLAC files that had an MP3 match.")

if __name__ == "__main__":
    main()
