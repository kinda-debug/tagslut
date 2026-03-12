#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import quote

from mutagen.id3 import ID3
from mutagen.mp3 import MP3


def _tag_text(tags: ID3, *keys: str) -> str | None:
    for key in keys:
        frame = tags.get(key)
        if frame is None:
            continue
        text = getattr(frame, "text", None)
        if text:
            value = str(text[0]).strip()
            if value:
                return value
    return None


def _track_number(tags: ID3) -> str | None:
    raw = _tag_text(tags, "TRCK")
    if not raw:
        return None
    return raw.split("/", 1)[0].strip() or None


def _file_uri(path: Path) -> str:
    return "file://localhost" + quote(path.resolve().as_posix())


@dataclass(frozen=True)
class TrackRow:
    track_id: int
    path: Path
    name: str
    artist: str
    album: str
    genre: str
    bpm: str
    key: str
    year: str
    track_number: str
    size: int
    total_time: str
    bitrate: str
    sample_rate: str
    date_added: str
    comments: str
    label: str
    mix: str
    remixer: str


def _read_track_row(track_id: int, path: Path) -> TrackRow:
    try:
        audio = MP3(path)
    except Exception:
        audio = None
    try:
        tags = ID3(path)
    except Exception:
        tags = None

    size = path.stat().st_size
    total_time = ""
    bitrate = ""
    sample_rate = ""
    if audio is not None and getattr(audio, "info", None) is not None:
        length = getattr(audio.info, "length", None)
        rate = getattr(audio.info, "bitrate", None)
        hz = getattr(audio.info, "sample_rate", None)
        if length:
            total_time = str(int(length))
        if rate:
            bitrate = str(int(rate / 1000))
        if hz:
            sample_rate = str(int(hz))

    name = path.stem
    artist = ""
    album = ""
    genre = ""
    bpm = ""
    key = ""
    year = ""
    track_number = ""
    comments = ""
    label = ""
    mix = ""
    remixer = ""
    if tags is not None:
        name = _tag_text(tags, "TIT2") or name
        artist = _tag_text(tags, "TPE1") or ""
        album = _tag_text(tags, "TALB") or ""
        genre = _tag_text(tags, "TCON") or ""
        bpm = _tag_text(tags, "TBPM") or ""
        key = _tag_text(tags, "TKEY", "TXXX:INITIALKEY") or ""
        year = _tag_text(tags, "TDRC", "TYER") or ""
        track_number = _track_number(tags) or ""
        comments = _tag_text(tags, "COMM::eng", "COMM") or ""
        label = _tag_text(tags, "TXXX:LABEL") or ""
        mix = _tag_text(tags, "TXXX:MIXNAME") or ""
        remixer = _tag_text(tags, "TPE4") or ""

    return TrackRow(
        track_id=track_id,
        path=path.resolve(),
        name=name,
        artist=artist,
        album=album,
        genre=genre,
        bpm=bpm,
        key=key,
        year=year,
        track_number=track_number,
        size=size,
        total_time=total_time,
        bitrate=bitrate,
        sample_rate=sample_rate,
        date_added=str(date.today()),
        comments=comments,
        label=label,
        mix=mix,
        remixer=remixer,
    )


def _iter_playlist_paths(path: Path) -> list[Path]:
    items: list[Path] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        items.append((path.parent / line).resolve())
    return items


def _indent(elem: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        for child in elem:
            _indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = indent + "  "
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = indent
    elif level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent


def build_rekordbox_xml(
    *,
    pool_root: Path,
    playlists_root: Path,
    output_path: Path,
    folder_name: str,
    product_name: str = "rekordbox",
    product_version: str = "7.2.11",
    company_name: str = "AlphaTheta",
    backup_existing: bool = True,
) -> dict[str, object]:
    pool_root = pool_root.expanduser().resolve()
    playlists_root = playlists_root.expanduser().resolve()
    output_path = output_path.expanduser().resolve()

    mp3_files = sorted(pool_root.rglob("*.mp3"))
    track_rows: list[TrackRow] = []
    track_ids_by_path: dict[Path, int] = {}
    for track_id, path in enumerate(mp3_files, start=1):
        row = _read_track_row(track_id, path)
        track_rows.append(row)
        track_ids_by_path[path.resolve()] = track_id

    playlist_files = sorted(playlists_root.glob("*.m3u"))
    playlist_rows: list[tuple[str, list[int]]] = []
    for playlist_path in playlist_files:
        track_ids: list[int] = []
        seen: set[int] = set()
        for item in _iter_playlist_paths(playlist_path):
            track_id = track_ids_by_path.get(item.resolve())
            if track_id is None or track_id in seen:
                continue
            seen.add(track_id)
            track_ids.append(track_id)
        playlist_rows.append((playlist_path.stem, track_ids))

    dj_playlists = ET.Element("DJ_PLAYLISTS", attrib={"Version": "1.0.0"})
    ET.SubElement(
        dj_playlists,
        "PRODUCT",
        attrib={"Name": product_name, "Version": product_version, "Company": company_name},
    )

    collection = ET.SubElement(dj_playlists, "COLLECTION", attrib={"Entries": str(len(track_rows))})
    for row in track_rows:
        attrs = {
            "TrackID": str(row.track_id),
            "Name": row.name,
            "Artist": row.artist,
            "Composer": "",
            "Album": row.album,
            "Grouping": "",
            "Genre": row.genre,
            "Kind": "MP3 File",
            "Size": str(row.size),
            "TotalTime": row.total_time,
            "DiscNumber": "1",
            "TrackNumber": row.track_number,
            "Year": row.year,
            "AverageBpm": row.bpm,
            "DateAdded": row.date_added,
            "BitRate": row.bitrate,
            "SampleRate": row.sample_rate,
            "Comments": row.comments,
            "PlayCount": "0",
            "Rating": "0",
            "Location": _file_uri(row.path),
            "Remixer": row.remixer,
            "Tonality": row.key,
            "Label": row.label,
            "Mix": row.mix,
        }
        clean_attrs = {key: value for key, value in attrs.items() if value is not None}
        track_node = ET.SubElement(collection, "TRACK", attrib=clean_attrs)
        if row.bpm:
            ET.SubElement(
                track_node,
                "TEMPO",
                attrib={"Inizio": "0.000", "Bpm": row.bpm, "Metro": "4/4", "Battito": "1"},
            )

    playlists_node = ET.SubElement(dj_playlists, "PLAYLISTS")
    root_node = ET.SubElement(playlists_node, "NODE", attrib={"Type": "0", "Name": "ROOT", "Count": "1"})
    folder_node = ET.SubElement(
        root_node,
        "NODE",
        attrib={"Type": "0", "Name": folder_name, "Count": str(len(playlist_rows))},
    )
    for playlist_name, track_ids in playlist_rows:
        playlist_node = ET.SubElement(
            folder_node,
            "NODE",
            attrib={"Type": "1", "Name": playlist_name, "KeyType": "0", "Entries": str(len(track_ids))},
        )
        for track_id in track_ids:
            ET.SubElement(playlist_node, "TRACK", attrib={"Key": str(track_id)})

    _indent(dj_playlists)

    backup_path: Path | None = None
    if output_path.exists() and backup_existing:
        backup_path = output_path.with_suffix(output_path.suffix + ".bak")
        counter = 1
        while backup_path.exists():
            backup_path = output_path.with_suffix(output_path.suffix + f".bak{counter}")
            counter += 1
        shutil.copy2(output_path, backup_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(dj_playlists).write(output_path, encoding="utf-8", xml_declaration=True)

    return {
        "output_path": str(output_path),
        "backup_path": str(backup_path) if backup_path is not None else "",
        "pool_root": str(pool_root),
        "playlists_root": str(playlists_root),
        "folder_name": folder_name,
        "tracks": len(track_rows),
        "playlists": len(playlist_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Rekordbox XML from a self-contained pool run.")
    parser.add_argument("--pool-root", required=True, help="Pool root containing copied MP3s")
    parser.add_argument("--playlists-root", required=True, help="Directory containing rewritten .m3u playlists")
    parser.add_argument("--output", required=True, help="Output Rekordbox XML path")
    parser.add_argument("--folder-name", required=True, help="Top-level playlist folder name inside Rekordbox XML")
    parser.add_argument("--product-name", default="rekordbox", help="PRODUCT Name attribute")
    parser.add_argument("--product-version", default="7.2.11", help="PRODUCT Version attribute")
    parser.add_argument("--company-name", default="AlphaTheta", help="PRODUCT Company attribute")
    parser.add_argument("--no-backup", action="store_true", help="Do not back up existing output XML")
    args = parser.parse_args()

    summary = build_rekordbox_xml(
        pool_root=Path(args.pool_root),
        playlists_root=Path(args.playlists_root),
        output_path=Path(args.output),
        folder_name=args.folder_name,
        product_name=args.product_name,
        product_version=args.product_version,
        company_name=args.company_name,
        backup_existing=not args.no_backup,
    )
    print(summary)


if __name__ == "__main__":
    main()
