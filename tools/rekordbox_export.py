#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


DB_PATH = Path("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
TEMPLATE_XML = Path("/Volumes/MUSIC/rekordbox_mp3.xml")
OUTPUT_DIR = Path("/Volumes/MUSIC")


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


def _file_uri(path_text: str) -> str:
    p = Path(path_text)
    posix = p.as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return "file://localhost" + quote(posix)


def _date_only(text: str | None) -> str:
    if text:
        candidate = str(text).strip()
        if len(candidate) >= 10 and candidate[4] == "-" and candidate[7] == "-":
            return candidate[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    base = OUTPUT_DIR / f"rekordbox_fresh_{stamp}.xml"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = OUTPUT_DIR / f"rekordbox_fresh_{stamp}_{counter}.xml"
        if not candidate.exists():
            return candidate
        counter += 1


@dataclass(frozen=True)
class Track:
    track_id: int
    name: str
    artist: str
    album: str
    total_time: str
    bitrate: str
    sample_rate: str
    location: str
    date_added: str


def _load_template_product() -> dict[str, str]:
    if not TEMPLATE_XML.exists():
        return {"Name": "tagslut", "Version": "3.0.0", "Company": "tagslut"}
    try:
        tree = ET.parse(TEMPLATE_XML)
        root = tree.getroot()
        product = root.find("PRODUCT")
        if product is None:
            return {"Name": "tagslut", "Version": "3.0.0", "Company": "tagslut"}
        attrib = dict(product.attrib)
        return {
            "Name": attrib.get("Name", "tagslut"),
            "Version": attrib.get("Version", "3.0.0"),
            "Company": attrib.get("Company", attrib.get("Name", "tagslut") or "tagslut"),
        }
    except Exception as exc:
        print(f"[template-error] {TEMPLATE_XML}: {exc}", file=sys.stderr, flush=True)
        return {"Name": "tagslut", "Version": "3.0.0", "Company": "tagslut"}


def _iter_tracks(db_path: Path) -> list[Track]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              ma.id AS track_id,
              ma.path AS path,
              COALESCE(ti.title_norm, '') AS title_norm,
              COALESCE(ti.artist_norm, '') AS artist_norm,
              COALESCE(ti.album_norm, '') AS album_norm,
              COALESCE(ma.duration_s, 0) AS duration_s,
              COALESCE(ma.bitrate, '') AS bitrate,
              COALESCE(ma.sample_rate, '') AS sample_rate,
              ma.created_at AS created_at
            FROM mp3_asset ma
            JOIN track_identity ti ON ti.id = ma.identity_id
            JOIN asset_file af ON af.id = ma.asset_id
            WHERE ma.zone = 'MP3_LIBRARY'
            ORDER BY ma.id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    tracks: list[Track] = []
    for r in rows:
        path_text = str(r["path"] or "").strip()
        title = str(r["title_norm"] or "").strip()
        artist = str(r["artist_norm"] or "").strip()
        album = str(r["album_norm"] or "").strip()
        duration_s = str(int(r["duration_s"] or 0))
        bitrate = str(r["bitrate"] or "").strip()
        sample_rate = str(r["sample_rate"] or "").strip()
        date_added = _date_only(r["created_at"])

        name = title or Path(path_text).stem
        location = _file_uri(path_text)
        tracks.append(
            Track(
                track_id=int(r["track_id"]),
                name=name,
                artist=artist,
                album=album,
                total_time=duration_s,
                bitrate=bitrate,
                sample_rate=sample_rate,
                location=location,
                date_added=date_added,
            )
        )
    return tracks


def main() -> int:
    tracks = _iter_tracks(DB_PATH)
    output_path = _output_path()

    dj_playlists = ET.Element("DJ_PLAYLISTS", attrib={"Version": "1.0.0"})
    ET.SubElement(dj_playlists, "PRODUCT", attrib=_load_template_product())

    collection = ET.SubElement(dj_playlists, "COLLECTION", attrib={"Entries": str(len(tracks))})
    for t in tracks:
        attrs = {
            "TrackID": str(t.track_id),
            "Name": t.name,
            "Artist": t.artist,
            "Album": t.album,
            "Kind": "MP3 File",
            "TotalTime": t.total_time,
            "BitRate": t.bitrate,
            "SampleRate": t.sample_rate,
            "Location": t.location,
            "DateAdded": t.date_added,
        }
        ET.SubElement(collection, "TRACK", attrib={k: v for k, v in attrs.items() if v != ""})

    playlists = ET.SubElement(dj_playlists, "PLAYLISTS")
    ET.SubElement(playlists, "NODE", attrib={"Name": "ROOT", "Type": "0", "Count": "0"})

    _indent(dj_playlists)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(dj_playlists).write(output_path, encoding="utf-8", xml_declaration=True)

    print(f"Rekordbox XML: {len(tracks)} tracks written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

