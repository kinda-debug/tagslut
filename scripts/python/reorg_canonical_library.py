#!/usr/bin/env python3
"""
Reorganize canonical FLACs to:
/Volumes/bad/FINAL_LIBRARY/Artist/(YYYY) Album Name/Artist - (YYYY) Album Name - [Disc#.]Track#. Title.flac
- Copies files to new structure
- Verifies copy (checksum)
- Deletes original if copy is verified
- Logs all actions
"""
import os
import sqlite3
import shutil
import hashlib
from pathlib import Path

DB = os.path.expanduser('~/dedupe_repo_reclone/artifacts/db/library_canonical_fresh.db')
ROOT = Path('/Volumes/bad/FINAL_LIBRARY')
LOG = Path('~/dedupe_repo_reclone/artifacts/logs/reorg_canonical.log').expanduser()

os.makedirs(LOG.parent, exist_ok=True)

def safe(val, default="[Unknown]"):
    if not val:
        return default
    return str(val).replace(':', '꞉').replace('/', '_').strip()

def get_year(*fields):
    for f in fields:
        if f and f[:4].isdigit():
            return f[:4]
    return 'XXXX'

def build_new_path(tags):
    artist = safe(tags.get('albumartist') or tags.get('artist'), '[Unknown Artist]')
    album = safe(tags.get('album'), '[Unknown Album]')
    year = get_year(tags.get('date'), tags.get('originalyear'), tags.get('originaldate'))
    disc = tags.get('discnumber')
    totaldiscs = tags.get('totaldiscs')
    track = tags.get('tracknumber')
    title = safe(tags.get('title'), '[Unknown Title]')
    # Directory
    dir_path = ROOT / artist / f"({year}) {album}"
    # Filename
    disc_part = f"{int(disc):02d}-" if disc and totaldiscs and int(totaldiscs) > 1 else ""
    track_part = f"{int(track):02d}" if track and track.isdigit() else "XX"
    fname = f"{artist} - ({year}) {album} - {disc_part}{track_part}. {title}.flac"
    return dir_path / fname

def checksum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT path, tags_json FROM library_files')
    rows = c.fetchall()
    moved = 0
    skipped = 0
    failed = 0
    with open(LOG, 'w') as log:
        for src, tags_json in rows:
            src = Path(src)
            if not src.exists():
                log.write(f"MISSING: {src}\n")
                failed += 1
                continue
            try:
                import json
                tags = json.loads(tags_json) if tags_json else {}
            except Exception:
                tags = {}
            dest = build_new_path(tags)
            if dest.exists():
                log.write(f"SKIP (exists): {dest}\n")
                skipped += 1
                continue
            os.makedirs(dest.parent, exist_ok=True)
            shutil.copy2(src, dest)
            if checksum(src) == checksum(dest):
                log.write(f"COPIED: {src} -> {dest}\n")
                src.unlink()
                log.write(f"DELETED: {src}\n")
                moved += 1
            else:
                log.write(f"FAILED COPY: {src} -> {dest}\n")
                dest.unlink(missing_ok=True)
                failed += 1
    print(f"Done. Moved: {moved}, Skipped: {skipped}, Failed: {failed}. Log: {LOG}")

if __name__ == "__main__":
    main()
