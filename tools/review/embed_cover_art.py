#!/usr/bin/env python3
"""
Embed cover art into audio files by reading best_cover_url/canonical_album_art_url from DB.
Supports FLAC and MP3 via mutagen.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, APIC, error as ID3Error
from mutagen.mp3 import MP3

def fetch_bytes(url: str, timeout: int = 30) -> Optional[bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None

def get_cover_url(conn: sqlite3.Connection, path: str) -> Optional[str]:
    cur = conn.cursor()
    row = cur.execute(
        """
        SELECT lt.best_cover_url, f.canonical_album_art_url
        FROM files f
        LEFT JOIN library_tracks lt ON lt.library_track_key = f.library_track_key
        WHERE f.path = ?
        """,
        (path,),
    ).fetchone()
    if not row:
        return None
    return row[0] or row[1]

def detect_mime(img_bytes: bytes) -> str:
    if img_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if img_bytes.startswith(b"\x89PNG"):
        return "image/png"
    return "image/jpeg"

def embed_flac(path: Path, img_bytes: bytes, mime: str, force: bool) -> bool:
    audio = FLAC(str(path))
    if audio.pictures and not force:
        return False
    if force:
        audio.clear_pictures()
    pic = Picture()
    pic.data = img_bytes
    pic.type = 3  # front cover
    pic.mime = mime
    audio.add_picture(pic)
    audio.save()
    return True

def embed_mp3(path: Path, img_bytes: bytes, mime: str, force: bool) -> bool:
    audio = MP3(str(path))
    try:
        tags = audio.tags or ID3()
    except ID3Error:
        tags = ID3()
    if tags.getall("APIC") and not force:
        return False
    if force:
        for apic in tags.getall("APIC"):
            tags.delall("APIC")
    tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img_bytes))
    tags.save(str(path))
    return True

def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.suffix.lower() in {".flac", ".mp3"} and p.is_file():
            yield p

def iter_from_paths_list(paths_file: Path) -> Iterable[Path]:
    for line in paths_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        p = Path(line)
        if p.suffix.lower() in {".flac", ".mp3"} and p.is_file():
            yield p

def iter_from_move_log(move_log: Path) -> Iterable[Path]:
    for line in move_log.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        dest = rec.get("dest")
        if not dest:
            continue
        p = Path(dest)
        if p.suffix.lower() in {".flac", ".mp3"} and p.is_file():
            yield p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", help="Root folder to scan")
    ap.add_argument("--paths", help="Text file with one absolute path per line")
    ap.add_argument("--move-log", help="JSONL move log with dest paths")
    ap.add_argument("--force", action="store_true", help="Replace existing art")
    ap.add_argument("--execute", action="store_true", help="Write changes")
    args = ap.parse_args()

    if not args.root and not args.paths and not args.move_log:
        ap.error("--root, --paths, or --move-log is required")
    conn = sqlite3.connect(args.db)
    updated = 0
    skipped = 0
    missing = 0

    if args.paths:
        paths_iter = iter_from_paths_list(Path(args.paths))
    elif args.move_log:
        paths_iter = iter_from_move_log(Path(args.move_log))
    else:
        paths_iter = iter_files(Path(args.root))

    for path in paths_iter:
        cover_url = get_cover_url(conn, str(path))
        if not cover_url:
            missing += 1
            continue
        img = fetch_bytes(cover_url)
        if not img:
            missing += 1
            continue
        mime = detect_mime(img)

        if not args.execute:
            updated += 1
            continue

        try:
            if path.suffix.lower() == ".flac":
                ok = embed_flac(path, img, mime, args.force)
            else:
                ok = embed_mp3(path, img, mime, args.force)
            if ok:
                updated += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    print(f"updated={updated} skipped={skipped} missing={missing}")

if __name__ == "__main__":
    main()
