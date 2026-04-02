from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from mutagen import id3


SCHEMA_A = re.compile(
    r"^(?P<artist>.+?) – \((?P<year>\d{4})\) (?P<album>.+?) – (?P<track>\d+) (?P<title>.+)$"
)
SCHEMA_B = re.compile(r"^(?P<artist>.+?) - (?P<title>.+)$")
BPM_SUFFIX = re.compile(r"\s*\(\d{2,3}\)\s*$")


@dataclass
class ParsedFilename:
    artist: str
    title: str
    album: str | None
    year: str | None
    track: str | None
    schema: str


@dataclass
class Stats:
    scanned: int = 0
    already_tagged: int = 0
    schema_a_fixed: int = 0
    schema_b_fixed: int = 0
    unparseable: int = 0


def parse_filename(stem: str) -> ParsedFilename | None:
    match_a = SCHEMA_A.match(stem)
    if match_a:
        return ParsedFilename(
            artist=match_a["artist"],
            title=match_a["title"],
            album=match_a["album"],
            year=match_a["year"],
            track=match_a["track"],
            schema="A",
        )

    match_b = SCHEMA_B.match(stem)
    if match_b:
        raw_title = match_b["title"].strip()
        title = BPM_SUFFIX.sub("", raw_title).strip()
        return ParsedFilename(
            artist=match_b["artist"],
            title=title,
            album=None,
            year=None,
            track=None,
            schema="B",
        )

    return None


def _text_present(frame: object | None) -> bool:
    if frame is None:
        return False
    text = getattr(frame, "text", None)
    if text is None:
        return False
    if isinstance(text, str):
        return bool(text.strip())
    if isinstance(text, (list, tuple)):
        return any(str(item).strip() for item in text)
    return bool(text)


def _load_tags(path: Path) -> id3.ID3:
    try:
        return id3.ID3(str(path))
    except id3.ID3NoHeaderError:
        return id3.ID3()


def _write_frames(tags: id3.ID3, parsed: ParsedFilename) -> None:
    tags.delall("TPE1")
    tags.setall("TPE1", [id3.TPE1(encoding=3, text=[parsed.artist])])

    tags.delall("TIT2")
    tags.setall("TIT2", [id3.TIT2(encoding=3, text=[parsed.title])])

    if parsed.album:
        tags.delall("TALB")
        tags.setall("TALB", [id3.TALB(encoding=3, text=[parsed.album])])

    if parsed.year:
        tags.delall("TDRC")
        tags.setall("TDRC", [id3.TDRC(encoding=3, text=[parsed.year])])

    if parsed.track:
        tags.delall("TRCK")
        tags.setall("TRCK", [id3.TRCK(encoding=3, text=[parsed.track])])


def process_path(path: Path, execute: bool, verbose: bool, stats: Stats) -> None:
    stats.scanned += 1

    tags = _load_tags(path)
    if _text_present(tags.get("TPE1")) and _text_present(tags.get("TIT2")):
        stats.already_tagged += 1
        if verbose:
            print(f"[skip] already tagged: {path}")
        return

    parsed = parse_filename(path.stem)
    if not parsed:
        stats.unparseable += 1
        if verbose:
            print(f"[skip] unparseable filename: {path}")
        return

    if parsed.schema == "A":
        stats.schema_a_fixed += 1
    else:
        stats.schema_b_fixed += 1

    if execute:
        _write_frames(tags, parsed)
        tags.save(str(path), v2_version=3)
        if verbose:
            print(f"[write] {parsed.schema} -> {path}")
    elif verbose:
        print(f"[dry-run] {parsed.schema} -> {path}")


def iter_mp3_paths(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".mp3":
            yield path


def run(root: Path, execute: bool, verbose: bool) -> Stats:
    stats = Stats()
    for path in iter_mp3_paths(root):
        process_path(path, execute=execute, verbose=verbose, stats=stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write missing ID3 tags to MP3s using filename metadata",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Volumes/MUSIC/MP3_LIBRARY"),
        help="directory to scan recursively",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually write tags (default: dry-run)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print one line per file",
    )

    args = parser.parse_args(argv)
    stats = run(args.root, execute=args.execute, verbose=args.verbose)

    print(
        "Scanned: {stats.scanned}, already tagged: {stats.already_tagged}, "
        "schema A fixed: {stats.schema_a_fixed}, schema B fixed: {stats.schema_b_fixed}, "
        "unparseable: {stats.unparseable}".format(stats=stats)
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
