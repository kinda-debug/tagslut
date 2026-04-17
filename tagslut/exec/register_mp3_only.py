from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from mutagen import id3, mp3

from tagslut.core.hashing import calculate_file_hash
from tagslut.storage.models import AudioFile
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import dual_write_enabled, dual_write_registered_file
from tagslut.zones import Zone, coerce_zone, determine_zone


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


def _infer_library(path: Path) -> str:
    resolved = path.expanduser().resolve()
    if str(resolved).startswith("/Volumes/MUSIC/Albums/"):
        return "SPOTIFLAC_MOBILE"
    for part in resolved.parts:
        if part == "MP3_LIBRARY":
            return "MP3_LIBRARY"
        if part == "MASTER_LIBRARY":
            return "MASTER_LIBRARY"
    return "default"


def _default_zone_for_path(path: Path) -> Zone:
    library = _infer_library(path)
    if library == "MP3_LIBRARY":
        return Zone.ACCEPTED
    return determine_zone(integrity_ok=True, is_duplicate=False, file_path=path)


def _load_existing_paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT path FROM files").fetchall()
    return {str(row[0]) for row in rows}


def _iter_mp3(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".mp3":
            yield path


def extract_mp3_audio(
    path: Path,
    *,
    library: str | None = None,
    zone: str | None = None,
) -> AudioFile:
    path = path.expanduser().resolve()
    st = path.stat()
    tags = _load_tags(path)
    metadata = _extract_metadata_from_tags(tags)
    _maybe_parse_from_filename(path, metadata)
    _maybe_isrc_from_filename(path, metadata)

    audio = mp3.MP3(str(path))
    duration = float(getattr(audio.info, "length", 0.0) or 0.0)
    sample_rate = int(getattr(audio.info, "sample_rate", 0) or 0)
    bitrate = int(getattr(audio.info, "bitrate", 0) or 0)
    sha256 = calculate_file_hash(path)
    resolved_library = library or _infer_library(path)
    resolved_zone = coerce_zone(zone) or _default_zone_for_path(path)

    return AudioFile(
        path=path,
        checksum=sha256,
        sha256=sha256,
        duration=duration,
        bit_depth=0,
        sample_rate=sample_rate,
        bitrate=bitrate,
        metadata=metadata,
        flac_ok=None,
        library=resolved_library,
        zone=resolved_zone,
        mtime=st.st_mtime,
        size=st.st_size,
        original_path=path,
    )


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
        if execute:
            init_db(conn)
        existing_paths = _load_existing_paths(conn)
        dual_write_v3 = bool(execute and dual_write_enabled())

        for path in _iter_mp3(root):
            stats.scanned += 1
            path_str = str(path.resolve())
            if path_str in existing_paths:
                stats.skipped_existing += 1
                if verbose:
                    print(f"[skip] already in DB: {path_str}")
                continue

            try:
                audio = extract_mp3_audio(path, zone=zone)
                metadata_json = json.dumps(audio.metadata or {}, ensure_ascii=False, sort_keys=True)
                now_iso = datetime.now(timezone.utc).isoformat()

                if not execute:
                    if verbose:
                        print(f"[dry-run] would insert: {path_str}")
                    continue

                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO files (
                        path,
                        checksum,
                        sha256,
                        library,
                        zone,
                        mtime,
                        size,
                        sample_rate,
                        bitrate,
                        download_source,
                        flac_ok,
                        duration,
                        metadata_json,
                        original_path,
                        mgmt_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        path_str,
                        audio.checksum,
                        audio.sha256,
                        audio.library,
                        audio.zone.value if audio.zone else zone,
                        audio.mtime,
                        audio.size,
                        audio.sample_rate,
                        audio.bitrate,
                        source,
                        None,
                        audio.duration,
                        metadata_json,
                        str(audio.original_path or audio.path),
                        "new",
                    ),
                )
                if dual_write_v3:
                    dual_write_registered_file(
                        conn,
                        path=path_str,
                        content_sha256=audio.sha256,
                        streaminfo_md5=None,
                        checksum=audio.checksum,
                        size_bytes=audio.size,
                        mtime=audio.mtime,
                        duration_s=audio.duration,
                        sample_rate=audio.sample_rate,
                        bit_depth=audio.bit_depth,
                        bitrate=audio.bitrate,
                        library=audio.library,
                        zone=audio.zone.value if audio.zone else zone,
                        download_source=source,
                        download_date=now_iso,
                        mgmt_status="new",
                        metadata=audio.metadata,
                        duration_ref_ms=None,
                        duration_ref_source=source,
                        event_time=now_iso,
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
