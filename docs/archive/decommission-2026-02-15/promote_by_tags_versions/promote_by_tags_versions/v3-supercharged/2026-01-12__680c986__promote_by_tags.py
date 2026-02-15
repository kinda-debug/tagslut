#!/usr/bin/env python3
"""
Promote FLAC files into a canonical layout using tags.

Dry-run by default; use --execute to copy/move files.
Naming rules match the Picard template:
  - Top folder: label (if compilation) else albumartist/artist
  - Album folder: (YYYY) Album + optional [Bootleg]/[Live]/[Compilation]/[Soundtrack]/[EP]/[Single]
  - Filename: NN. <Artist - >Title with featuring -> feat.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Iterable, TextIO

from mutagen import MutagenError  # type: ignore[attr-defined]
from mutagen.flac import FLAC, FLACNoHeaderError

TRUTHY = {"1", "true", "yes", "y", "t"}


def normalize_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, bytes):
            out.append(item.decode("utf-8", errors="ignore"))
        else:
            out.append(str(item))
    return [v for v in out if v]


def load_tags(path: Path) -> dict[str, list[str]]:
    audio = FLAC(path)
    tags: dict[str, list[str]] = {}
    if audio.tags and hasattr(audio.tags, "items"):
        for key, value in audio.tags.items():
            tags[key.lower()] = normalize_values(value)
    return tags


def first_tag(tags: dict[str, list[str]], keys: Iterable[str]) -> str:
    for key in keys:
        vals = tags.get(key)
        if vals:
            return vals[0]
    return ""


def tag_values(tags: dict[str, list[str]], keys: Iterable[str]) -> list[str]:
    out: list[str] = []
    for key in keys:
        out.extend(tags.get(key, []))
    return out


def is_truthy(value: str) -> bool:
    return value.strip().lower() in TRUTHY


def extract_year(*candidates: str) -> str:
    for value in candidates:
        if not value:
            continue
        match = re.search(r"\d{4}", value)
        if match:
            return match.group(0)
    return "0000"


def parse_track_number(value: str) -> str:
    if not value:
        return "00"
    match = re.search(r"\d+", value)
    if not match:
        return "00"
    return f"{int(match.group(0)):02d}"


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sanitize_component(text: str, fallback: str) -> str:
    cleaned = collapse_ws(text)
    cleaned = cleaned.replace("/", " - ").replace("\\", " - ").replace("\x00", "")
    cleaned = cleaned.strip(" .")
    return cleaned or fallback


def normalize_title(title: str) -> str:
    out = re.sub(r"\s+featuring\s+", " feat. ", title, flags=re.IGNORECASE)
    out = re.sub(r"\s+ft\.\s+", " feat. ", out, flags=re.IGNORECASE)
    out = out.replace("feat. feat.", "feat.")
    return collapse_ws(out)


def parse_release_types(tags: dict[str, list[str]]) -> tuple[set[str], str]:
    raw_types = tag_values(tags, ["releasetype", "musicbrainz_albumtype", "albumtype"])
    types: set[str] = set()
    for raw in raw_types:
        for part in re.split(r"[;,/]", raw):
            part = part.strip().lower()
            if part:
                types.add(part)
    primary = first_tag(
        tags,
        [
            "_primaryreleasetype",
            "primaryreleasetype",
            "musicbrainz_primaryreleasetype",
        ],
    ).strip().lower()
    if not primary:
        if "ep" in types:
            primary = "ep"
        elif "single" in types:
            primary = "single"
    return types, primary


def build_destination(tags: dict[str, list[str]], dest_root: Path) -> Path:
    types, primary = parse_release_types(tags)
    compilation_flag = is_truthy(first_tag(tags, ["compilation", "itunescompilation"]))
    compilation = compilation_flag or ("compilation" in types)

    label = first_tag(tags, ["label"])
    albumartist = first_tag(tags, ["albumartist", "album artist"])
    artist = first_tag(tags, ["artist"])
    album = first_tag(tags, ["album"])
    title = first_tag(tags, ["title"])
    date = first_tag(tags, ["date"])
    originaldate = first_tag(tags, ["originaldate"])

    top = label if compilation else (albumartist or artist)
    top = sanitize_component(top, "Various Artists" if compilation else "Unknown Artist")

    year = extract_year(date, originaldate)
    album_folder = sanitize_component(f"({year}) {album}".strip(), "Unknown Album")

    suffix = ""
    if "bootleg" in types:
        suffix = " [Bootleg]"
    elif "live" in types:
        suffix = " [Live]"
    elif "compilation" in types:
        suffix = " [Compilation]"
    elif "soundtrack" in types:
        suffix = " [Soundtrack]"
    elif primary == "ep":
        suffix = " [EP]"
    elif primary == "single":
        suffix = " [Single]"

    album_folder = sanitize_component(album_folder + suffix, "Unknown Album")

    track_number = parse_track_number(first_tag(tags, ["tracknumber", "track"]))
    title = normalize_title(title or "Unknown Title")
    if compilation and artist:
        title = f"{artist} - {title}"
    title = sanitize_component(title, "Unknown Title")

    filename = f"{track_number}. {title}.flac"
    return dest_root / top / album_folder / filename


def hash_sources(sources: list[Path]) -> str:
    h = hashlib.sha256()
    for path in sources:
        h.update(path.as_posix().encode("utf-8", errors="ignore"))
        h.update(b"\n")
    return h.hexdigest()


def load_resume(
    resume_file: Path | None,
    sources_hash: str,
    total: int,
    dest_root: Path,
    mode: str,
    log: callable,
) -> int:
    if not resume_file or not resume_file.exists():
        return 0
    try:
        state = json.loads(resume_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log(f"[RESUME] Could not read resume file: {resume_file}", always=True)
        return 0
    if state.get("sources_hash") != sources_hash:
        log(f"[RESUME] Source list changed; ignoring resume: {resume_file}", always=True)
        return 0
    if state.get("total") != total:
        log(f"[RESUME] Total changed; ignoring resume: {resume_file}", always=True)
        return 0
    if Path(state.get("dest_root", "")) != dest_root:
        log(f"[RESUME] Dest root changed; ignoring resume: {resume_file}", always=True)
        return 0
    if state.get("mode") != mode:
        log(f"[RESUME] Mode changed; ignoring resume: {resume_file}", always=True)
        return 0
    return int(state.get("index", 0))


def save_resume(
    resume_file: Path | None,
    index: int,
    total: int,
    sources_hash: str,
    dest_root: Path,
    mode: str,
    log: callable,
) -> None:
    if not resume_file:
        return
    state = {
        "index": index,
        "total": total,
        "sources_hash": sources_hash,
        "dest_root": str(dest_root),
        "mode": mode,
    }
    try:
        resume_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        log(f"[RESUME] Failed to write resume file: {resume_file}", always=True)


def collect_sources(source_root: Path | None, paths_from_file: Path | None) -> list[Path]:
    if source_root and paths_from_file:
        raise ValueError("Cannot use both --source-root and --paths-from-file")
    if not source_root and not paths_from_file:
        raise ValueError("Either --source-root or --paths-from-file is required")

    sources: list[Path] = []
    if paths_from_file:
        for line in paths_from_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            path = Path(candidate)
            if path.suffix.lower() != ".flac":
                continue
            sources.append(path)
    else:
        assert source_root is not None
        for path in source_root.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".flac":
                sources.append(path)
    return sorted(sources)


def process(
    sources: list[Path],
    dest_root: Path,
    mode: str,
    execute: bool,
    skip_existing: bool,
    skip_missing: bool,
    skip_errors: bool,
    progress_every: int,
    log_file: TextIO | None,
    progress_only: bool,
    resume_file: Path | None,
) -> None:
    def log(message: str, *, always: bool = False) -> None:
        if not progress_only or always:
            print(message)
        if log_file:
            log_file.write(message + "\n")
            log_file.flush()

    total = len(sources)
    sources_hash = hash_sources(sources)
    resume_from = load_resume(resume_file, sources_hash, total, dest_root, mode, log)
    if resume_from:
        log(f"[RESUME] Starting from {resume_from + 1}/{total}", always=True)

    copied = 0
    moved = 0
    skipped_existing = 0
    skipped_missing = 0
    skipped_duplicate = 0
    tag_errors = 0
    seen_targets: set[Path] = set()

    log(
        f"Start run: total={total} mode={mode} execute={execute} "
        f"skip_existing={skip_existing} skip_missing={skip_missing} skip_errors={skip_errors}",
        always=True,
    )
    try:
        for index, source in enumerate(sources, start=1):
            if resume_from and index <= resume_from:
                continue
            if skip_missing and not source.exists():
                skipped_missing += 1
                log(f"[SKIP MISSING] {source}")
                save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
                continue
            try:
                tags = load_tags(source)
            except (FLACNoHeaderError, MutagenError, ValueError) as exc:
                tag_errors += 1
                log(f"[TAG ERROR] {source} -> {exc}")
                if not skip_errors:
                    raise
                save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
                continue
            dest = build_destination(tags, dest_root)
            if dest == source:
                log(f"[SKIP SAME] {source}")
                save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
                continue
            if dest in seen_targets:
                skipped_duplicate += 1
                log(f"[SKIP DUPLICATE] {source} -> {dest}")
                save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
                continue
            seen_targets.add(dest)
            if skip_existing and dest.exists():
                skipped_existing += 1
                log(f"[SKIP EXISTS] {source} -> {dest}")
                save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
                continue

            if execute:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if mode == "copy":
                    shutil.copy2(source, dest)
                    copied += 1
                    log(f"[COPY] {source} -> {dest}")
                else:
                    shutil.move(source, dest)
                    moved += 1
                    log(f"[MOVE] {source} -> {dest}")
            else:
                prefix = "COPY" if mode == "copy" else "MOVE"
                log(f"[DRY {prefix}] {source} -> {dest}")

            if progress_every and index % progress_every == 0:
                remaining = max(total - index, 0)
                log(
                    f"[PROGRESS] processed {index}/{total} "
                    f"(COPY {copied}, MOVE {moved}, remaining {remaining})",
                    always=True,
                )
            save_resume(resume_file, index, total, sources_hash, dest_root, mode, log)
    except KeyboardInterrupt:
        log(
            f"\nInterrupted. Summary so far: COPY {copied}, MOVE {moved}, "
            f"SKIP {skipped_existing + skipped_missing + skipped_duplicate}, ERR {tag_errors}",
            always=True,
        )
        save_resume(resume_file, index if "index" in locals() else resume_from, total, sources_hash, dest_root, mode, log)
        return

    skipped_total = skipped_existing + skipped_missing + skipped_duplicate
    log(
        f"Summary: COPY {copied}, MOVE {moved}, SKIP {skipped_total}, ERR {tag_errors} (execute={execute})",
        always=True,
    )
    save_resume(resume_file, total, total, sources_hash, dest_root, mode, log)


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote FLACs into a canonical layout (dry-run by default).")
    parser.add_argument("--source-root", help="Root folder to scan for FLACs (e.g. staging keep dir)")
    parser.add_argument("--paths-from-file", help="File with newline-separated FLAC paths")
    parser.add_argument(
        "--dest-root",
        required=True,
        help="Destination library root (e.g. /Volumes/COMMUNE/M/Library)",
    )
    parser.add_argument(
        "--mode",
        choices=["move", "copy"],
        default="move",
        help="Use move or copy when --execute is set (default: move)",
    )
    parser.add_argument("--execute", action="store_true", help="Perform filesystem changes")
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip when the target already exists (default: True)",
    )
    parser.add_argument(
        "--skip-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip missing sources instead of aborting (default: True)",
    )
    parser.add_argument(
        "--skip-errors",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip tag read errors instead of aborting (default: True)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print a progress line every N processed files (0 to disable)",
    )
    parser.add_argument("--log-file", help="Append all output to this file")
    parser.add_argument("--no-log-file", action="store_true", help="Disable log file output")
    parser.add_argument(
        "--progress-only",
        action="store_true",
        help="Only print progress and summary to stdout (use log file for details)",
    )
    parser.add_argument("--resume-file", help="Path to resume state file (JSON)")
    parser.add_argument("--no-resume", action="store_true", help="Disable resume state tracking")
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser() if args.source_root else None
    paths_from_file = Path(args.paths_from_file).expanduser() if args.paths_from_file else None
    dest_root = Path(args.dest_root).expanduser()
    sources = collect_sources(source_root, paths_from_file)

    log_file = None
    if not args.no_log_file:
        if args.log_file:
            log_path = Path(args.log_file).expanduser()
        else:
            log_path = Path("/Users/georgeskhawam/Projects/tagslut/artifacts/M/03_reports/promote_by_tags.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")

    resume_path = None
    if not args.no_resume:
        resume_path = Path(args.resume_file).expanduser() if args.resume_file else Path(
            "/Users/georgeskhawam/Projects/tagslut/artifacts/M/03_reports/promote_by_tags.resume.json"
        )

    try:
        process(
            sources=sources,
            dest_root=dest_root,
            mode=args.mode,
            execute=args.execute,
            skip_existing=args.skip_existing,
            skip_missing=args.skip_missing,
            skip_errors=args.skip_errors,
            progress_every=max(args.progress_every, 0),
            log_file=log_file,
            progress_only=args.progress_only,
            resume_file=resume_path,
        )
    finally:
        if log_file:
            log_file.close()


if __name__ == "__main__":
    main()
