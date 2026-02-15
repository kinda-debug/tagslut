#!/usr/bin/env python3
"""
Promote FLAC files into a canonical layout using tags.

FIXED VERSION:
- Enforces Roon-safe release identity
- RELEASETYPE is authoritative
- Singles can NEVER land in album folders
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).parents[2]))

from mutagen.flac import FLAC
from tagslut.utils.console_ui import ConsoleUI
from tagslut.utils.file_operations import FileOperations
from tagslut.utils.safety_gates import SafetyGates
from tagslut.utils.db import open_db, resolve_db_path
from tagslut.metadata.canon import load_canon_rules, apply_canon

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
    for v in (date, originaldate):
        if v:
            m = re.match(r"(\d{4})", v)
            if m:
                return m.group(1)
    return "0000"


def sanitize_component(value, fallback):
    value = (value or "").strip()
    value = re.sub(r"[\\/]", "-", value)
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
    FIX:
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

def build_destination(tags, dest_root):
    types, primary = parse_release_types(tags)

    compilation = is_truthy(first_tag(tags, ["compilation", "itunescompilation"])) or "compilation" in types

    albumartist = first_tag(tags, ["albumartist", "album artist"])
    artist = first_tag(tags, ["artist"])
    album = first_tag(tags, ["album"])
    title = first_tag(tags, ["title"])
    date = first_tag(tags, ["date"])
    originaldate = first_tag(tags, ["originaldate"])

    top = albumartist or artist or "Unknown Artist"
    if compilation:
        top = "Various Artists"

    top = sanitize_component(top, "Unknown Artist")

    year = extract_year(date, originaldate)

    suffix = {
        "single": " [Single]",
        "ep": " [EP]",
        "album": "",
        "compilation": " [Compilation]",
    }.get(primary, "")

    album_folder = sanitize_component(f"({year}) {album}{suffix}", "Unknown Album")

    # SAFETY: never allow single/ep to land in bare album folder
    if primary in {"single", "ep"} and suffix == "":
        album_folder = sanitize_component(f"({year}) {album} [{primary.upper()}]", "Unknown Album")

    track = first_tag(tags, ["tracknumber", "track"]) or "1"
    track = track.split("/")[0].zfill(2)

    title = sanitize_component(title or "Unknown Title", "Unknown Title")

    filename = limit_filename(f"{track}. {title}.flac")

    return dest_root / top / album_folder / filename


# ---------------------------
# MAIN
# ---------------------------

def truncate_path(path: Path, max_len: int = 50) -> str:
    """Truncate path from the left, keeping the most relevant parts."""
    s = str(path)
    if len(s) <= max_len:
        return s
    return "…" + s[-(max_len - 1):]


def main():
    parser = argparse.ArgumentParser(
        description="Promote FLAC files into Artist/Album/Track layout using tags."
    )
    parser.add_argument("sources", nargs="+", type=Path,
                        help="FLAC files or directories to process")
    parser.add_argument("--dest", required=True, type=Path,
                        help="Destination root directory")
    parser.add_argument("--canon", dest="canon", action="store_true",
                        help="Apply canonical tag rules (default)")
    parser.add_argument("--no-canon", dest="canon", action="store_false",
                        help="Skip canonical tag rules")
    parser.set_defaults(canon=True)
    parser.add_argument("--canon-rules", type=Path,
                        help="Path to canon rules JSON (default: tools/rules/library_canon.json)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform copies (default is dry-run)")
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

            dest = build_destination(promo_tags, args.dest)

            # Extract artist/album for display
            artist = first_tag(promo_tags, ["albumartist", "album artist", "artist"]) or "Unknown"
            album = first_tag(promo_tags, ["album"]) or "Unknown"
            title = first_tag(promo_tags, ["title"]) or src.name

            # Compact output: show progress and key info
            ui.print(f"[{i:4d}/{total}] {artist[:25]:<25} │ {album[:30]:<30} │ {title[:30]}")
            ops.safe_copy(src, dest)
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
            # Shorten common mutagen errors
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
        ui.print("Run with --execute to perform actual copies")


if __name__ == "__main__":
    main()
