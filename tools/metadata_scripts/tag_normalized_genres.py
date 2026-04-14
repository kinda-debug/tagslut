#!/usr/bin/env python3
"""
Normalize genre tags using tagslut genre normalization rules.

Uses shared GenreNormalizer (tagslut.metadata.genre_normalization) for consistent
tag processing with normalize_genres.py.

Two supported modes:

1) Apple Music MP3 mode (recommended for this workflow)
   - Invoked via `--root /path/to/library`
   - Reads and writes only the ID3 `TCON` (genre) field
   - `--dry-run` reports changes without writing

2) Legacy FLAC mode (Beatport-compatible tags)
   - Invoked via positional `path` argument
   - Writes GENRE/SUBGENRE/GENRE_PREFERRED/GENRE_FULL when `--execute` is set

Output Tags (Beatport-compatible format):
    - GENRE: Primary genre (e.g., "House")
    - SUBGENRE: Style/sub-genre (e.g., "Deep House")
    - GENRE_PREFERRED: Preferred for cascading
    - GENRE_FULL: Hierarchical format "genre | style"

Usage:
    # Apple Music MP3 library: dry-run (TCON only)
    python tools/metadata_scripts/tag_normalized_genres.py \\
      --root "/Volumes/MUSIC/Music/Media.localized/Music/" \\
      --dry-run

    # Apple Music MP3 library: execute (TCON only)
    python tools/metadata_scripts/tag_normalized_genres.py \\
      --root "/Volumes/MUSIC/Music/Media.localized/Music/"

For combined workflows (DB backfill + in-place tags), pair with normalize_genres.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import mutagen
    import mutagen.id3
except Exception as e:
    raise SystemExit("mutagen is required (pip install mutagen)") from e

# Add tagslut package to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tagslut.metadata.genre_normalization import GenreNormalizer


def iter_flac_paths(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    return [p for p in root.rglob("*.flac") if not p.name.startswith("._")]

def iter_mp3_paths(root: Path) -> List[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".mp3" else []
    return [p for p in root.rglob("*.mp3") if not p.name.startswith("._")]


def get_id3_genre(id3: mutagen.id3.ID3) -> Optional[str]:
    frame = id3.get("TCON")
    if frame is None:
        return None
    if not getattr(frame, "text", None):
        return None
    # Keep the genre string as-is (Apple Music library is expected to have a flat field).
    return str(frame.text[0]).strip() if frame.text else None


def set_id3_genre(id3: mutagen.id3.ID3, genre: str) -> None:
    encoding = 3
    existing = id3.get("TCON")
    if existing is not None and hasattr(existing, "encoding"):
        encoding = existing.encoding
    id3.setall("TCON", [mutagen.id3.TCON(encoding=encoding, text=[genre])])


def delete_id3_genre(id3: mutagen.id3.ID3) -> None:
    if "TCON" in id3:
        del id3["TCON"]


def normalize_id3_tcon(
    normalizer: GenreNormalizer, raw_genre: Optional[str]
) -> Tuple[Optional[str], bool]:
    if raw_genre is None:
        return None, False
    normalized = normalizer.normalize_value(raw_genre, "genre")
    if normalized == raw_genre:
        return raw_genre, False
    # Empty-string means "delete"
    if normalized == "":
        return None, True
    return normalized, True


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize genre tags using tools/rules/genre_normalization.json")
    ap.add_argument("path", type=Path, nargs="?", help="Legacy FLAC mode: root path to scan (FLAC) or a single file")
    ap.add_argument("--root", type=Path, help="Apple Music MP3 mode: root path to scan (MP3)")
    ap.add_argument("--rules", type=Path, default=Path("tools/rules/genre_normalization.json"))
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing (Apple Music MP3 mode)")
    ap.add_argument("--execute", action="store_true", help="Write tags in-place")
    ap.add_argument("--limit", type=int, help="Limit number of files")
    args = ap.parse_args()

    normalizer = GenreNormalizer(args.rules)

    if args.root is not None:
        root = args.root.expanduser().resolve()
        mp3s = iter_mp3_paths(root)
        if args.limit:
            mp3s = mp3s[: args.limit]
        if not mp3s:
            print("No MP3 files found.")
            return 1

        scanned = 0
        changed = 0
        deleted = 0
        updated = 0

        for idx, p in enumerate(mp3s, start=1):
            scanned += 1
            try:
                id3 = mutagen.id3.ID3(str(p))
            except mutagen.id3.ID3NoHeaderError:
                continue
            except Exception:
                continue

            raw = get_id3_genre(id3)
            normalized, is_change = normalize_id3_tcon(normalizer, raw)
            if not is_change:
                continue

            changed += 1
            if normalized is None:
                deleted += 1
                print(f"CHANGE {p}: {raw} -> [none]")
                if not args.dry_run:
                    delete_id3_genre(id3)
            else:
                updated += 1
                print(f"CHANGE {p}: {raw} -> {normalized}")
                if not args.dry_run:
                    set_id3_genre(id3, normalized)

            if not args.dry_run:
                try:
                    id3.save(str(p), v2_version=3)
                except Exception:
                    pass

            if idx % 250 == 0 or idx == len(mp3s):
                print(f"[{idx}/{len(mp3s)}] {p.name}")

        print(f"Scanned:  {scanned}")
        print(f"Changed:  {changed}")
        print(f"Updated:  {updated}")
        print(f"Deleted:  {deleted}")
        print(f"Dry-run:  {bool(args.dry_run)}")
        return 0

    if args.path is None:
        ap.error("Either provide --root (MP3 mode) or a positional path (FLAC mode).")

    root = args.path.expanduser().resolve()
    flacs = iter_flac_paths(root)
    if args.limit:
        flacs = flacs[: args.limit]

    if not flacs:
        print("No FLAC files found.")
        return 0

    changed = 0
    for idx, p in enumerate(flacs, start=1):
        try:
            audio = mutagen.File(str(p), easy=False)
        except Exception:
            continue
        if audio is None or audio.tags is None:
            continue
        tags = audio.tags

        norm_genre, norm_style, _ = normalizer.choose_normalized(tags)
        if not norm_genre:
            continue

        if args.execute:
            normalizer.apply_tags_to_file(audio, norm_genre, norm_style)
            changed += 1

        if idx % 50 == 0 or idx == len(flacs):
            print(f"[{idx}/{len(flacs)}] {p.name}")

    print(f"Scanned: {len(flacs)}")
    print(f"Tagged:  {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
