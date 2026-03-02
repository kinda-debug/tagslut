#!/usr/bin/env python3
"""
Promote FLAC files into a canonical layout using tags.

Move-only policy:
- No copy mode. Files are moved after verification.
- Temporary files are removed after success.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import subprocess
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from mutagen.flac import FLAC  # noqa: E402
from tagslut.utils.console_ui import ConsoleUI  # noqa: E402
from tagslut.utils.file_operations import FileOperations  # noqa: E402
from tagslut.utils.safety_gates import SafetyGates  # noqa: E402
from tagslut.metadata.canon import load_canon_rules, apply_canon  # noqa: E402
from tagslut.utils.final_library_layout import (  # noqa: E402
    FinalLibraryLayoutError,
    build_final_library_destination,
)
from _progress import ProgressTracker  # noqa: E402

TRUTHY = {"1", "true", "yes", "y", "t"}
_AUDIO_EXT_RE = re.compile(r"\.(flac|aiff?|wav|mp3|m4a)$", re.IGNORECASE)


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


def strip_audio_ext(value: str) -> str:
    text = (value or "").strip()
    while True:
        stripped = _AUDIO_EXT_RE.sub("", text).strip()
        if stripped == text:
            return stripped
        text = stripped


def normalize_tags_for_promote(tags):
    """Ensure tag values are lists (mutagen-style) for downstream helpers."""
    out = {}
    for k, v in tags.items():
        if isinstance(v, (list, tuple)):
            out[k] = list(v)
        else:
            out[k] = [str(v)]
    return out


def flac_test_ok(path: Path) -> tuple[bool, str | None]:
    try:
        res = subprocess.run(
            ["flac", "-t", "--silent", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False, "flac binary missing"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if res.returncode == 0:
        return True, None
    err = (res.stderr or res.stdout or "").strip()
    return False, err[:400] or "flac -t failed"


def duration_ok(conn: sqlite3.Connection, path: Path) -> tuple[bool, str]:
    row = conn.execute("SELECT duration_status FROM files WHERE path = ?", (str(path),)).fetchone()
    if not row:
        return False, "duration_status=missing"
    status = (row[0] or "").strip().lower()
    if status == "ok":
        return True, "duration_status=ok"
    return False, f"duration_status={status or 'unknown'}"


def db_entry_exists(conn: sqlite3.Connection, path: Path) -> bool:
    row = conn.execute("SELECT 1 FROM files WHERE path = ?", (str(path),)).fetchone()
    return bool(row)


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


def build_destination(tags, dest_root, is_dj=False):
    types, primary = parse_release_types(tags)

    compilation = (
        is_truthy(first_tag(tags, ["compilation", "itunescompilation"]))
        or "compilation" in types
    )

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
    top = (
        (label or "Various Artists")
        if compilation
        else (albumartist or artist or "Unknown Artist")
    )
    top = sanitize_component(top, "Unknown Artist")

    year = extract_year(date, originaldate)
    album = sanitize_component(album or "Unknown Album", "Unknown Album")
    title = sanitize_component(title or "Unknown Title", "Unknown Title")
    artist = sanitize_component(artist or "Unknown Artist", "Unknown Artist")

    title = strip_audio_ext(title)
    artist = strip_audio_ext(artist)

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
    parser.add_argument(
        "--final-library",
        action="store_true",
        help=(
            "Use strict FINAL_LIBRARY naming convention "
            "(albumartist/(year) album/artist – (year) album – discTrack title.flac)"
        ),
    )
    parser.add_argument("--canon", dest="canon", action="store_true",
                        help="Apply canonical tag rules (default)")
    parser.add_argument("--no-canon", dest="canon", action="store_false",
                        help="Skip canonical tag rules")
    parser.set_defaults(canon=True)
    parser.add_argument("--canon-rules", type=Path,
                        help="Path to canon rules JSON (default: tools/rules/library_canon.json)")
    parser.add_argument("--dj-only", action="store_true",
                        help="Treat sources as DJ material (use label for compilations)")
    parser.add_argument(
        "--skip-flac-test",
        action="store_true",
        help="Skip flac -t integrity test (default: run and block corrupt files)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="SQLite DB path for duration_status checks (defaults to $TAGSLUT_DB if set)",
    )
    parser.add_argument(
        "--allow-non-ok-duration",
        action="store_true",
        help="Allow promotion when duration_status is not ok (default: block when DB is available)",
    )
    parser.add_argument(
        "--require-db-entry",
        action="store_true",
        help="Skip files that do not exist in DB (recommended with --allow-non-ok-duration)",
    )
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing destination files")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform moves (default is dry-run)")
    parser.add_argument(
        "--move-log",
        type=Path,
        help="JSONL move audit log path (default: artifacts/logs/file_move.jsonl)",
    )
    parser.add_argument("--progress-interval", type=int, default=50,
                        help="Progress print interval with remaining/ETA")
    args = parser.parse_args()

    ui = ConsoleUI()
    gates = SafetyGates(ui=ui)
    ops = FileOperations(
        ui=ui,
        gates=gates,
        dry_run=not args.execute,
        quiet=True,
        audit_log_path=args.move_log,
    )

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
    progress = ProgressTracker(total=total, interval=int(args.progress_interval), label="Promote")

    success_count = 0
    skip_count = 0
    integrity_skip = 0
    duration_skip = 0
    error_count = 0
    errors = []

    db_conn = None
    db_path = args.db or Path(os.environ.get("TAGSLUT_DB", "")).expanduser()
    if db_path and str(db_path) and db_path.exists():
        db_conn = sqlite3.connect(str(db_path))
    elif args.db:
        ui.warning(f"DB path not found for duration checks: {db_path}")
    else:
        ui.warning("No DB configured; duration_status checks are skipped.")

    canon_rules = None
    if args.canon:
        rules_path = args.canon_rules or (
            Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json"
        )
        canon_rules = load_canon_rules(rules_path)

    for i, src in enumerate(files_to_process, 1):
        try:
            if not args.skip_flac_test:
                ok, err = flac_test_ok(src)
                if not ok:
                    integrity_skip += 1
                    skip_count += 1
                    errors.append((src.name, f"FLAC integrity failed: {err}"))
                    ui.print(f"[{i:4d}/{total}] SKIP: {src.name[:50]} (corrupt FLAC)")
                    if progress.should_print(i):
                        ui.print(
                            progress.line(
                                i,
                                extra=f"moved={success_count} skipped={skip_count} errors={error_count}",
                            )
                        )
                    continue

            if db_conn is not None:
                if args.require_db_entry and not db_entry_exists(db_conn, src):
                    skip_count += 1
                    errors.append((src.name, "DB gate failed: missing DB row"))
                    ui.print(f"[{i:4d}/{total}] SKIP: {src.name[:50]} (db_entry=missing)")
                    if progress.should_print(i):
                        ui.print(
                            progress.line(
                                i,
                                extra=f"moved={success_count} skipped={skip_count} errors={error_count}",
                            )
                        )
                    continue

                if not args.allow_non_ok_duration:
                    ok, reason = duration_ok(db_conn, src)
                    if not ok:
                        duration_skip += 1
                        skip_count += 1
                        errors.append((src.name, f"Duration gate failed: {reason}"))
                        ui.print(f"[{i:4d}/{total}] SKIP: {src.name[:50]} ({reason})")
                        if progress.should_print(i):
                            ui.print(
                                progress.line(
                                    i,
                                    extra=f"moved={success_count} skipped={skip_count} errors={error_count}",
                                )
                            )
                        continue

            audio = FLAC(src)
            raw_tags = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
            if canon_rules:
                canon_tags = apply_canon(raw_tags, canon_rules)
            else:
                canon_tags = raw_tags
            promo_tags = normalize_tags_for_promote(canon_tags)

            is_dj = args.dj_only or is_truthy(first_tag(promo_tags, ["dedupe_dj", "dj"]))
            if args.final_library:
                if args.dj_only:
                    ui.warning("--dj-only is ignored with --final-library")
                layout = build_final_library_destination(canon_tags, args.dest)
                dest = layout.dest_path
            else:
                dest = build_destination(promo_tags, args.dest, is_dj=is_dj)

            # Extract artist/album for display
            artist = first_tag(promo_tags, ["albumartist", "album artist", "artist"]) or "Unknown"
            album = first_tag(promo_tags, ["album"]) or "Unknown"
            title = first_tag(promo_tags, ["title"]) or src.name

            ui.print(f"[{i:4d}/{total}] {artist[:25]:<25} │ {album[:30]:<30} │ {title[:30]}")
            moved = ops.safe_move(src, dest, skip_confirmation=True, allow_overwrite=args.force)
            if not moved:
                skip_count += 1
                if progress.should_print(i):
                    ui.print(progress.line(i, extra=f"moved={success_count} skipped={skip_count} errors={error_count}"))
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

            if progress.should_print(i):
                ui.print(progress.line(i, extra=f"moved={success_count} skipped={skip_count} errors={error_count}"))

        except Exception as e:
            error_count += 1
            error_msg = str(e)
            if "not a valid FLAC" in error_msg:
                error_msg = "Invalid FLAC file"
            if isinstance(e, FinalLibraryLayoutError):
                error_msg = f"Final layout error: {error_msg}"
            errors.append((src.name, error_msg))
            ui.print(f"[{i:4d}/{total}] SKIP: {src.name[:50]} ({error_msg})")
            if progress.should_print(i):
                ui.print(progress.line(i, extra=f"moved={success_count} skipped={skip_count} errors={error_count}"))

    # Summary
    ui.print("-" * 70)
    ui.print("\nSummary:")
    ui.print(f"  Processed: {success_count}")
    if skip_count:
        ui.print(f"  Skipped:   {skip_count}")
    if integrity_skip:
        ui.print(f"  Integrity blocked: {integrity_skip}")
    if duration_skip:
        ui.print(f"  Duration blocked: {duration_skip}")
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

    if db_conn is not None:
        db_conn.close()


if __name__ == "__main__":
    main()
