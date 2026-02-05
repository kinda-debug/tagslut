#!/usr/bin/env python3
"""
Promote FLAC files into a canonical layout using tags.

Move-only policy:
- No copy mode. Files are moved after verification.
- Temporary files are removed after success.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from mutagen.flac import FLAC
from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.file_operations import FileOperations
from dedupe.utils.safety_gates import SafetyGates
from dedupe.metadata.canon import load_canon_rules, apply_canon

TRUTHY = {"1", "true", "yes", "y", "t"}


# ---------------------------
# TAG HELPERS
# ---------------------------

def tag_values(tags, keys):
    out = []
    for k in keys:
        if k in tags:
            val = tags[k]
            if isinstance(val, (list, tuple)):
                out.extend(val)
            else:
                out.append(val)
    return out


def first_tag(tags, keys):
    for k in keys:
        if k in tags and tags[k]:
            val = tags[k]
            if isinstance(val, (list, tuple)):
                return str(val[0]).strip()
            return str(val).strip()
    return ""


def is_truthy(value):
    return str(value).strip().lower() in TRUTHY


def extract_year(date, originaldate):
    for v in (originaldate, date):
        if v:
            m = re.match(r"(\d{4})", v)
            if m:
                return m.group(1)
    return "0000"


def sanitize_component(value, fallback):
    value = (value or "").strip()
    value = re.sub(r"[\\/]", " - ", value)
    value = re.sub(r"[:*?\"<>|]", "", value)
    return value if value else fallback


def limit_filename(name, limit=240):
    return name[:limit]


def normalize_tags_for_promote(tags):
    """Ensure tag values are lists (mutagen-style) for downstream helpers."""
    out = {}
    for k, v in tags.items():
        if isinstance(v, (list, tuple)):
            out[k] = list(v)
        else:
            out[k] = [str(v)]
    return out


# ---------------------------
# FIXED RELEASE TYPE LOGIC
# ---------------------------

def parse_release_types(tags):
    """
    - RELEASETYPE tag is authoritative
    - TOTALTRACKS=1 forces single
    - Never allows silent fallback to album
    """
    raw_types = set()

    # Explicit RELEASETYPE (user-controlled)
    explicit = first_tag(tags, ["releasetype"])
    if explicit:
        raw_types.add(explicit.lower().strip())

    # Picard compatibility: recover release type if releasetype was unset
    if not explicit:
        primary = first_tag(tags, ["_primaryreleasetype"])
        if primary:
            explicit = primary.lower().strip()
            raw_types.add(explicit)

    # MusicBrainz fallbacks
    for raw in tag_values(tags, ["musicbrainz_albumtype", "albumtype"]):
        for part in re.split(r"[;,/]", raw):
            part = part.strip().lower()
            if part:
                raw_types.add(part)

    totaltracks = first_tag(tags, ["totaltracks", "totaltrack"])
    try:
        totaltracks = int(totaltracks)
    except Exception:
        totaltracks = None

    if "single" in raw_types:
        return raw_types, "single"

    if "ep" in raw_types:
        return raw_types, "ep"

    if totaltracks == 1:
        raw_types.add("single")
        return raw_types, "single"

    # If RELEASETYPE exists but is not recognised, keep it explicit to avoid album collisions
    if explicit and explicit.lower() not in {"album", "single", "ep", "compilation"}:
        return raw_types, explicit.lower().strip()

    return raw_types, "album"


# ---------------------------
# DESTINATION BUILDER (FIXED)
# ---------------------------

def _looks_like_artist_list(value: str, min_commas: int = 3) -> bool:
    return value.count(",") >= min_commas


def _looks_like_artist_list(value: str, min_commas: int = 3) -> bool:
    return value.count(",") >= min_commas


def build_destination(tags, dest_root, is_dj=False):
    types, primary = parse_release_types(tags)

    compilation = is_truthy(first_tag(tags, ["compilation", "itunescompilation"])) or "compilation" in types

    albumartist = first_tag(tags, ["albumartist", "album artist"])
    artist = first_tag(tags, ["artist"])
    label = first_tag(tags, ["label", "publisher", "organization", "recordlabel"])
    album = first_tag(tags, ["album"])
    title = first_tag(tags, ["title"])
    date = first_tag(tags, ["date"])
    originaldate = first_tag(tags, ["originaldate"])
    disc = first_tag(tags, ["discnumber", "disc"])

    # Treat huge artist lists as compilations for DJ material.
    if is_dj and label and _looks_like_artist_list(albumartist):
        compilation = True

    # Picard-style: compilation uses label (or Various Artists), otherwise albumartist.
    top = (label or "Various Artists") if compilation else (albumartist or artist or "Unknown Artist")
    top = sanitize_component(top, "Unknown Artist")

    year = extract_year(date, originaldate)
    album = sanitize_component(album or "Unknown Album", "Unknown Album")
    title = sanitize_component(title or "Unknown Title", "Unknown Title")

    # Release-type suffixes.
    type_suffix = {
        "single": " [Single]",
        "ep": " [EP]",
        "compilation": " [Compilation]",
        "album": "",
    }.get(primary, "")

    if compilation and type_suffix != " [Compilation]":
        type_suffix = " [Compilation]"

    album_folder = sanitize_component(f"({year}) {album}{type_suffix}", "Unknown Album")

    track = (first_tag(tags, ["tracknumber", "track"]) or "1").split("/")[0].zfill(2)
    disc = (disc.split("/")[0].zfill(1)) if disc else "1"

    filename = limit_filename(f"{disc}-{track}. {artist} - {title}.flac")

    return dest_root / top / album_folder / filename


# ---------------------------
# MAIN
# ---------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Promote FLAC files into Artist/Album/Track layout using tags (move-only)."
    )
    parser.add_argument("sources", nargs="+", type=Path,
                        help="FLAC files or directories to process")
    parser.add_argument("--dest", required=True, type=Path,
                        help="Destination root directory (e.g., .../dj or .../archive)")
    parser.add_argument("--canon", dest="canon", action="store_true",
                        help="Apply canonical tag rules (default)")
    parser.add_argument("--no-canon", dest="canon", action="store_false",
                        help="Skip canonical tag rules")
    parser.set_defaults(canon=True)
    parser.add_argument("--canon-rules", type=Path,
                        help="Path to canon rules JSON (default: tools/rules/library_canon.json)")
    parser.add_argument("--dj-only", action="store_true",
                        help="Treat sources as DJ material (use label for compilations)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform moves (default is dry-run)")
    args = parser.parse_args()

    ui = ConsoleUI()
    gates = SafetyGates(ui=ui)
    ops = FileOperations(ui=ui, gates=gates, dry_run=not args.execute, quiet=True)

    # Expand directories to individual FLAC files
    files_to_process = []
    for src in args.sources:
        if src.is_dir():
            files_to_process.extend(src.rglob("*.flac"))
        else:
            files_to_process.append(src)

    total = len(files_to_process)
    if total == 0:
        ui.warning("No FLAC files found to process")
        return

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    ui.print(f"\n[{mode}] Processing {total} files → {args.dest}\n")
    ui.print("-" * 70)

    success_count = 0
    skip_count = 0
    error_count = 0
    errors = []

    canon_rules = None
    if args.canon:
        rules_path = args.canon_rules or (Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json")
        canon_rules = load_canon_rules(rules_path)

    for i, src in enumerate(files_to_process, 1):
        try:
            audio = FLAC(src)
            raw_tags = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
            if canon_rules:
                canon_tags = apply_canon(raw_tags, canon_rules)
            else:
                canon_tags = raw_tags
            promo_tags = normalize_tags_for_promote(canon_tags)

            is_dj = args.dj_only or is_truthy(first_tag(promo_tags, ["dedupe_dj", "dj"]))
            dest = build_destination(promo_tags, args.dest, is_dj=is_dj)

            # Extract artist/album for display
            artist = first_tag(promo_tags, ["albumartist", "album artist", "artist"]) or "Unknown"
            album = first_tag(promo_tags, ["album"]) or "Unknown"
            title = first_tag(promo_tags, ["title"]) or src.name

            ui.print(f"[{i:4d}/{total}] {artist[:25]:<25} │ {album[:30]:<30} │ {title[:30]}")
            moved = ops.safe_move(src, dest, skip_confirmation=True)
            if not moved:
                skip_count += 1
                continue

            if args.execute and canon_rules:
                dest_audio = FLAC(dest)
                dest_audio.clear()
                for key, value in canon_tags.items():
                    if isinstance(value, (list, tuple)):
                        dest_audio[key] = [str(v) for v in value]
                    else:
                        dest_audio[key] = str(value)
                dest_audio.save()
            success_count += 1

        except Exception as e:
            error_count += 1
            error_msg = str(e)
            if "not a valid FLAC" in error_msg:
                error_msg = "Invalid FLAC file"
            errors.append((src.name, error_msg))
            ui.print(f"[{i:4d}/{total}] SKIP: {src.name[:50]} ({error_msg})")

    # Summary
    ui.print("-" * 70)
    ui.print("\nSummary:")
    ui.print(f"  Processed: {success_count}")
    if skip_count:
        ui.print(f"  Skipped:   {skip_count}")
    if error_count:
        ui.print(f"  Errors:    {error_count}")

    if errors and len(errors) <= 10:
        ui.print("\nFailed files:")
        for fname, err in errors:
            ui.print(f"  • {fname}: {err}")
    elif errors:
        ui.print("\n(First 10 errors shown)")
        for fname, err in errors[:10]:
            ui.print(f"  • {fname}: {err}")

    ui.print("")
    if args.execute:
        ui.success("Promotion complete")
    else:
        ui.print("Run with --execute to perform actual moves")


if __name__ == "__main__":
    main()
