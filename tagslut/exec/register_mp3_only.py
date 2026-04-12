from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from mutagen import id3, mp3


SCHEMA_A = re.compile(
    r"^(?P<artist>.+?) – \((?P<year>\d{4})\) (?P<album>.+?) – (?P<track>\d+) (?P<title>.+)$"
)
SCHEMA_B = re.compile(r"^(?P<artist>.+?) - (?P<title>.+)$")
BPM_SUFFIX = re.compile(r"\s*\(\d{2,3}\)\s*$")
ISRC_IN_BRACKETS = re.compile(r"\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]", re.IGNORECASE)


@dataclass
class ParsedFilename:
    artist: str
    title: str
    album: Optional[str]
    year: Optional[str]
    track: Optional[str]


@dataclass
class Stats:
    scanned: int = 0
    skipped_existing: int = 0
    inserted: int = 0
    failed: int = 0


def parse_filename(stem: str) -> ParsedFilename | None:
    match_a = SCHEMA_A.match(stem)
    if match_a:
        return ParsedFilename(
            artist=match_a["artist"].strip(),
            title=match_a["title"].strip(),
            album=match_a["album"].strip(),
            year=match_a["year"].strip(),
            track=match_a["track"].strip(),
        )

    match_b = SCHEMA_B.match(stem)
    if match_b:
        raw_title = match_b["title"].strip()
        title = BPM_SUFFIX.sub("", raw_title).strip()
        return ParsedFilename(
            artist=match_b["artist"].strip(),
            title=title,
            album=None,
            year=None,
            track=None,
        )

    return None


def _first_text(frame: object | None) -> str:
    if frame is None:
        return ""
    text = getattr(frame, "text", None)
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        return str(text[0]).strip() if text else ""
    return str(text).strip()


def _load_tags(path: Path) -> id3.ID3:
    try:
        return id3.ID3(str(path))
    except id3.ID3NoHeaderError:
        return id3.ID3()


def _extract_metadata_from_tags(tags: id3.ID3) -> Dict[str, str]:
    mapping = {
        "artist": _first_text(tags.get("TPE1")),
        "title": _first_text(tags.get("TIT2")),
        "album": _first_text(tags.get("TALB")),
        "date": _first_text(tags.get("TDRC")),
        "tracknumber": _first_text(tags.get("TRCK")),
        "isrc": _first_text(tags.get("TSRC")),
        "bpm": _first_text(tags.get("TBPM")),
        "key": _first_text(tags.get("TKEY")),
        "genre": _first_text(tags.get("TCON")),
        "label": _first_text(tags.get("TPUB")),
    }
    return {k: v for k, v in mapping.items() if v}


def _maybe_parse_from_filename(path: Path, metadata: Dict[str, str]) -> None:
    if metadata.get("artist") and metadata.get("title"):
        return
    parsed = parse_filename(path.stem)
    if not parsed:
        return
    metadata.setdefault("artist", parsed.artist)
    metadata.setdefault("title", parsed.title)
    if parsed.album:
        metadata.setdefault("album", parsed.album)
    if parsed.year:
        metadata.setdefault("date", parsed.year)
    if parsed.track:
        metadata.setdefault("tracknumber", parsed.track)


def _duration_seconds(path: Path) -> Optional[int]:
    try:
        audio = mp3.MP3(str(path))
        length = getattr(audio.info, "length", None)
        if length is None:
            return None
        return int(length)
    except Exception:
        return None


def _maybe_isrc_from_filename(path: Path, metadata: Dict[str, str]) -> Optional[str]:
    if metadata.get("isrc"):
        return metadata["isrc"].strip().upper()
    match = ISRC_IN_BRACKETS.search(path.stem)
    if match:
        value = match.group(1).strip().upper()
        metadata.setdefault("isrc", value)
        return value
    return None


def _load_existing_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT path FROM files").fetchall()
    return {str(row[0]) for row in rows}


def _iter_mp3(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".mp3":
            yield path


def register_mp3_only(
    root: Path,
    db_path: Path | None,
    source: str,
    zone: str,
    execute: bool,
    verbose: bool,
) -> Stats:
    if db_path is None:
        env_db = os.environ.get("TAGSLUT_DB")
        if not env_db:
            raise SystemExit("Database path required: pass --db or set TAGSLUT_DB")
        db_path = Path(env_db)

    root = root.expanduser().resolve()
    db_path = db_path.expanduser().resolve()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats = Stats()

    try:
        existing_paths = _load_existing_paths(conn)

        for path in _iter_mp3(root):
            stats.scanned += 1
            path_str = str(path.resolve())
            if path_str in existing_paths:
                stats.skipped_existing += 1
                if verbose:
                    print(f"[skip] already in DB: {path_str}")
                continue

            try:
                tags = _load_tags(path)
                metadata = _extract_metadata_from_tags(tags)
                _maybe_parse_from_filename(path, metadata)
                isrc_value = _maybe_isrc_from_filename(path, metadata)

                duration = _duration_seconds(path)

                if not execute:
                    if verbose:
                        print(f"[dry-run] would insert: {path_str}")
                    continue

                metadata_json = json.dumps(metadata, ensure_ascii=False)

                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO files (
                        path,
                        zone,
                        download_source,
                        flac_ok,
                        duration,
                        metadata_json,
                        canonical_isrc,
                        ingestion_method,
                        ingestion_source,
                        ingestion_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path_str,
                        zone,
                        source,
                        None,
                        duration,
                        metadata_json,
                        isrc_value,
                        "legacy_mp3_register",
                        path_str,
                        "uncertain",
                    ),
                )
                inserted = (conn.total_changes - before) > 0
                stats.inserted += int(inserted)
                existing_paths.add(path_str)
                if verbose:
                    print(f"[insert] {path_str}")
            except Exception as exc:  # pragma: no cover - defensive
                stats.failed += 1
                if verbose:
                    print(f"[error] {path_str}: {exc}")

        if execute:
            conn.commit()
    finally:
        conn.close()

    print(
        "Scanned: {stats.scanned}, already in DB: {stats.skipped_existing}, "
        "inserted: {stats.inserted}, failed: {stats.failed}".format(stats=stats)
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register MP3-only DJ files into DB")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/Volumes/MUSIC/DJ_LIBRARY"),
        help="directory to scan recursively",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        type=Path,
        default=None,
        help="database path (or $TAGSLUT_DB)",
    )
    parser.add_argument("--source", default="legacy_mp3", help="download_source label")
    parser.add_argument("--zone", default="accepted", help="zone to assign")
    parser.add_argument("--execute", action="store_true", help="actually insert (default: dry-run)")
    parser.add_argument("--verbose", action="store_true", help="print one line per file")

    args = parser.parse_args(argv)
    register_mp3_only(
        root=args.root,
        db_path=args.db_path,
        source=args.source,
        zone=args.zone,
        execute=args.execute,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
