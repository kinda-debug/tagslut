import os
import sqlite3
import hashlib
import subprocess
from pathlib import Path

SCAN_ROOT = os.environ.get('SCAN_ROOT', '/Volumes/bad/FINAL_LIBRARY')
DB_OUT = os.environ.get('DB_OUT', 'library_canonical_fresh.db')

conn = sqlite3.connect(DB_OUT)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS library_files (
    path TEXT PRIMARY KEY,
    checksum TEXT,
    duration REAL,
    artist TEXT,
    album TEXT,
    title TEXT
)''')
conn.commit()

flac_files = list(Path(SCAN_ROOT).rglob('*.flac'))
total = len(flac_files)
print(f"Scanning {total} FLAC files in {SCAN_ROOT}...\n")
for idx, fpath in enumerate(flac_files, 1):
    path = str(fpath)
    # Check if file is already indexed
    c.execute('SELECT checksum FROM library_files WHERE path=?', (path,))
    row = c.fetchone()
    if row:
        # Calculate current checksum
        with open(path, 'rb') as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        if row[0] == checksum:
            print(f"[{idx}/{total}] SKIP (already indexed, unchanged): {path}")
            continue
        else:
            print(f"[{idx}/{total}] REPROCESS (checksum changed): {path}")
    else:
        print(f"[{idx}/{total}] NEW: {path}")
    # Calculate checksum
    with open(path, 'rb') as f:
        checksum = hashlib.sha256(f.read()).hexdigest()
    # Get duration and tags using metaflac (edit if you use another tool)
    try:
        out = subprocess.check_output([
            'metaflac', '--show-total-samples', '--show-sample-rate', '--show-tag=ARTIST', '--show-tag=ALBUM', '--show-tag=TITLE', path
        ], text=True)
        lines = out.splitlines()
        samples = int([l for l in lines if l.isdigit()][0])
        rate = int([l for l in lines if l.isdigit()][1])
        duration = samples / rate if rate else None
        artist = next((l.split('=')[1] for l in lines if l.startswith('ARTIST=')), None)
        album = next((l.split('=')[1] for l in lines if l.startswith('ALBUM=')), None)
        title = next((l.split('=')[1] for l in lines if l.startswith('TITLE=')), None)
    except Exception as e:
        print(f"  [WARN] Could not extract metadata: {e}")
        duration = None
        artist = album = title = None
    print(f"  Checksum: {checksum}")
    print(f"  Duration: {duration}")
    print(f"  Artist: {artist}")
    print(f"  Album: {album}")
    print(f"  Title: {title}\n")
    c.execute('INSERT OR REPLACE INTO library_files VALUES (?, ?, ?, ?, ?, ?)',
              (path, checksum, duration, artist, album, title))
    conn.commit()
conn.close()
print("\nScan complete.")
