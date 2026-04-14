#!/usr/bin/env python3
from __future__ import annotations

import csv
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4


LOCATIONS = {
    "staging_spotiflacnext": Path("/Volumes/MUSIC/staging/SpotiFLACnext"),
    "staging_spotiflac": Path("/Volumes/MUSIC/staging/SpotiFLAC"),
    "staging_other": Path("/Volumes/MUSIC/staging"),
    "master_unresolved": Path("/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED"),
    "master_unresolved_from_library": Path("/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED_FROM_LIBRARY"),
    "mp3_library_spotiflac_next": Path("/Volumes/MUSIC/MP3_LIBRARY/_spotiflac_next"),
    "mp3_leftovers": Path("/Volumes/MUSIC/mp3_leftorvers"),
    "work_fix": Path("/Volumes/MUSIC/_work/fix"),
}
EXTENSIONS = {".flac", ".m4a", ".mp3"}
DB_PATH = Path("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
OUTPUT_DIR = Path("/Volumes/MUSIC/logs")
HEADER = [
    "location",
    "path",
    "ext",
    "size_bytes",
    "isrc",
    "upc",
    "artist",
    "title",
    "in_asset_file",
    "in_track_identity",
    "asset_zone",
    "identity_isrc_match",
]


@dataclass
class InventoryRow:
    location: str
    path: str
    ext: str
    size_bytes: int
    isrc: str
    upc: str
    artist: str
    title: str
    in_asset_file: int
    in_track_identity: int
    asset_zone: str
    identity_isrc_match: str


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _decode_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "text"):
        return _decode_text(getattr(value, "text"))
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8").strip()
        except UnicodeDecodeError:
            return value.decode("latin-1", "ignore").strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _decode_text(item)
            if text:
                return text
        return ""
    return str(value).strip()


def _normalize_isrc(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _normalize_upc(value: str) -> str:
    return value.strip()


def _id3_text(tags: ID3, key: str) -> str:
    frame = tags.get(key)
    if frame is None:
        return ""
    return _decode_text(frame)


def _id3_user_text(tags: ID3, desc: str) -> str:
    for frame in tags.getall("TXXX"):
        frame_desc = str(getattr(frame, "desc", "")).strip().upper()
        if frame_desc == desc.upper():
            return _decode_text(getattr(frame, "text", ""))
    return ""


def _mp4_first(tags: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _decode_text(tags.get(key))
        if text:
            return text
    return ""


def _read_tags(path: Path) -> tuple[str, str, str, str]:
    try:
        suffix = path.suffix.lower()
        if suffix == ".flac":
            tags = FLAC(path)
            isrc = _normalize_isrc(_decode_text(tags.get("isrc", [None])))
            upc = _normalize_upc(_decode_text(tags.get("upc", [None])))
            artist = _decode_text(tags.get("artist", [None]))
            title = _decode_text(tags.get("title", [None]))
            return isrc, upc, artist, title
        if suffix == ".m4a":
            audio = MP4(str(path))
            tags = getattr(audio, "tags", None) or {}
            isrc = _normalize_isrc(_mp4_first(tags, "----:com.apple.iTunes:ISRC", "----:com.apple.iTunes:TSRC"))
            upc = _normalize_upc(_mp4_first(tags, "----:com.apple.iTunes:UPC"))
            artist = _mp4_first(tags, "\xa9ART")
            title = _mp4_first(tags, "\xa9nam")
            return isrc, upc, artist, title
        if suffix == ".mp3":
            MP3(str(path))
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            isrc = _normalize_isrc(_id3_text(tags, "TSRC"))
            upc = _normalize_upc(_id3_user_text(tags, "UPC") or _id3_user_text(tags, "BARCODE"))
            artist = _id3_text(tags, "TPE1")
            title = _id3_text(tags, "TIT2")
            return isrc, upc, artist, title
    except Exception as exc:
        _stderr(f"[tag-error] {path}: {exc}")
    return "", "", "", ""


def _iter_location_files(location: str, root: Path) -> Iterator[Path]:
    if not root.exists():
        _stderr(f"[missing-location] {location}: {root}")
        return
    if location == "staging_other":
        for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if child.is_dir() and child.name in {"SpotiFLACnext", "SpotiFLAC"}:
                continue
            if child.is_file() and child.suffix.lower() in EXTENSIONS:
                yield child.resolve()
        return

    for path in sorted(root.rglob("*"), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EXTENSIONS:
            continue
        yield path.resolve()


def _load_db_state(db_path: Path) -> tuple[dict[str, str], set[str]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        asset_rows = conn.execute("SELECT path, COALESCE(zone, '') FROM asset_file").fetchall()
        identity_rows = conn.execute(
            "SELECT isrc FROM track_identity WHERE isrc IS NOT NULL AND TRIM(isrc) != ''"
        ).fetchall()
    finally:
        conn.close()

    asset_zones: dict[str, str] = {}
    for raw_path, zone in asset_rows:
        if raw_path is None:
            continue
        asset_zones[str(raw_path)] = str(zone or "")

    identity_isrcs = {
        normalized
        for (raw_isrc,) in identity_rows
        if (normalized := _normalize_isrc(str(raw_isrc or "")))
    }
    return asset_zones, identity_isrcs


def _output_path(now: datetime) -> Path:
    return OUTPUT_DIR / f"final_audit_{now.strftime('%Y%m%d_%H%M%S')}.tsv"


def _is_unaccounted_location(location: str) -> bool:
    if location.startswith("staging_"):
        return True
    if location.startswith("master_unresolved"):
        return True
    return False


def main() -> int:
    asset_zones, identity_isrcs = _load_db_state(DB_PATH)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    output_path = _output_path(now)

    total_files = 0
    per_location_remaining: dict[str, int] = {k: 0 for k in LOCATIONS}
    per_location_not_in_db: dict[str, int] = {k: 0 for k in LOCATIONS}
    per_location_no_isrc: dict[str, int] = {k: 0 for k in LOCATIONS}

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(HEADER)

        for location, root in LOCATIONS.items():
            for path in _iter_location_files(location, root):
                total_files += 1
                per_location_remaining[location] += 1
                if total_files % 500 == 0:
                    print(".", end="", file=sys.stderr, flush=True)

                size_bytes = path.stat().st_size
                isrc, upc, artist, title = _read_tags(path)
                path_str = str(path)
                in_asset_file = 1 if path_str in asset_zones else 0
                in_track_identity = 1 if isrc and isrc in identity_isrcs else 0
                asset_zone = asset_zones.get(path_str, "")
                identity_isrc_match = isrc if in_track_identity else ""

                if not in_asset_file:
                    per_location_not_in_db[location] += 1
                if not isrc:
                    per_location_no_isrc[location] += 1

                row = InventoryRow(
                    location=location,
                    path=path_str,
                    ext=path.suffix.lower(),
                    size_bytes=size_bytes,
                    isrc=isrc,
                    upc=upc,
                    artist=artist,
                    title=title,
                    in_asset_file=in_asset_file,
                    in_track_identity=in_track_identity,
                    asset_zone=asset_zone,
                    identity_isrc_match=identity_isrc_match,
                )
                writer.writerow(
                    [
                        row.location,
                        row.path,
                        row.ext,
                        row.size_bytes,
                        row.isrc,
                        row.upc,
                        row.artist,
                        row.title,
                        row.in_asset_file,
                        row.in_track_identity,
                        row.asset_zone,
                        row.identity_isrc_match,
                    ]
                )

    unaccounted = sum(
        per_location_remaining[loc] for loc in LOCATIONS if _is_unaccounted_location(loc)
    )

    print("")
    for location in LOCATIONS:
        remaining = per_location_remaining[location]
        not_in_db = per_location_not_in_db[location]
        no_isrc = per_location_no_isrc[location]
        print(f"{location:28} {remaining:5d} files remaining  ({not_in_db} not in DB, {no_isrc} no ISRC)")

    if unaccounted:
        print(f"WARNING: {unaccounted} files remain unaccounted for. Review logs before proceeding.")

    print(f"Output: {output_path}")
    print(f"Final audit: {total_files} total files across all locations, {unaccounted} unaccounted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

