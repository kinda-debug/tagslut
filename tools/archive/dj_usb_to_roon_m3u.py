#!/usr/bin/env python3
"""
Build a Roon M3U playlist that mirrors the current DJUSB contents.

- Scans DJUSB for MP3s
- Reads tags (artist/title/album)
- Maps to library FLAC paths via tagslut DB
- Writes M3U with library paths

Outputs:
- <out>.m3u (playlist)
- artifacts/dj_usb_roon_missing_<ts>.txt (unmatched MP3s)
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import tomllib
from mutagen.easyid3 import EasyID3
from mutagen import File as MutagenFile

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY_ROOT = Path("/Volumes/MUSIC/LIBRARY")
DEFAULT_USB_ROOT = Path("/Volumes/DJUSB")


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _get_db_path() -> str:
    env = os.environ.get("TAGSLUT_DB")
    if env:
        return str(Path(env).expanduser())
    config_path = REPO_ROOT / "config.toml"
    if config_path.exists():
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        path = (data.get("db") or {}).get("path")
        if path:
            return str(Path(path).expanduser())
    raise SystemExit("No DB path found (TAGSLUT_DB or config.toml)")


def _read_mp3_tags(path: Path) -> Tuple[str, str, str]:
    artist = title = album = ""
    try:
        tags = EasyID3(path)
        artist = (tags.get("artist") or [""])[0]
        title = (tags.get("title") or [""])[0]
        album = (tags.get("album") or [""])[0]
        return artist, title, album
    except Exception:
        pass

    try:
        audio = MutagenFile(path, easy=False)
    except Exception:
        return "", "", ""

    if audio and getattr(audio, "tags", None):
        tags = audio.tags

        def _first(keys):
            for k in keys:
                raw = tags.get(k)
                if not raw:
                    continue
                if isinstance(raw, list):
                    raw = raw[0]
                return str(raw).strip()
            return ""

        artist = _first(["TPE1", "ARTIST", "artist"]) or artist
        title = _first(["TIT2", "TITLE", "title"]) or title
        album = _first(["TALB", "ALBUM", "album"]) or album
    return artist, title, album


def build_db_index(conn: sqlite3.Connection, library_root: Path) -> Tuple[Dict[Tuple[str, str, str], str], Dict[Tuple[str, str], str]]:
    by_ata: Dict[Tuple[str, str, str], str] = {}
    by_at: Dict[Tuple[str, str], str] = {}

    rows = conn.execute(
        """
        SELECT path, canonical_artist, canonical_title, canonical_album, mtime
        FROM files
        WHERE path LIKE ? AND path LIKE '%.flac'
          AND canonical_artist IS NOT NULL
          AND canonical_title IS NOT NULL
        """,
        (f"{library_root}%",),
    ).fetchall()

    for path, artist, title, album, mtime in rows:
        a = _norm(str(artist or ""))
        t = _norm(str(title or ""))
        al = _norm(str(album or ""))
        if not a or not t:
            continue
        key3 = (a, t, al)
        key2 = (a, t)
        # Prefer most recent mtime if multiple matches
        if key3 not in by_ata:
            by_ata[key3] = path
        if key2 not in by_at:
            by_at[key2] = path
    return by_ata, by_at


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Roon M3U from DJUSB MP3s")
    ap.add_argument("--usb", type=Path, default=DEFAULT_USB_ROOT, help="DJUSB mount path")
    ap.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_ROOT, help="Library root path")
    ap.add_argument("--out", type=Path, default=DEFAULT_LIBRARY_ROOT / "DJUSB_ROON.m3u", help="Output M3U path")
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: TAGSLUT_DB/config.toml)")
    args = ap.parse_args()

    usb_root = args.usb.expanduser().resolve()
    library_root = args.library.expanduser().resolve()
    out_path = args.out.expanduser().resolve()

    if not usb_root.exists():
        raise SystemExit(f"USB path not found: {usb_root}")
    if not library_root.exists():
        raise SystemExit(f"Library path not found: {library_root}")

    db_path = str(args.db.expanduser()) if args.db else _get_db_path()
    if not Path(db_path).exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        by_ata, by_at = build_db_index(conn, library_root)
    finally:
        conn.close()

    mp3s = list(usb_root.rglob("*.mp3"))
    matched = []
    missing = []

    for mp3 in mp3s:
        artist, title, album = _read_mp3_tags(mp3)
        a = _norm(artist)
        t = _norm(title)
        al = _norm(album)
        if not a or not t:
            missing.append(str(mp3))
            continue
        key3 = (a, t, al)
        key2 = (a, t)
        path = by_ata.get(key3) or by_at.get(key2)
        if path:
            matched.append(path)
        else:
            missing.append(str(mp3))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("#EXTM3U\n" + "\n".join(matched) + "\n", encoding="utf-8")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    missing_path = REPO_ROOT / "artifacts" / f"dj_usb_roon_missing_{ts}.txt"
    missing_path.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")

    print(f"MP3s scanned: {len(mp3s)}")
    print(f"Matched:      {len(matched)}")
    print(f"Missing:      {len(missing)}")
    print(f"M3U: {out_path}")
    print(f"Missing list: {missing_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
