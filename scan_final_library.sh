#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
SRC_DB="$REPO/artifacts/db/library_canonical_full.db"
SCAN_ROOT="/Volumes/bad/FINAL_LIBRARY"
DB_OUT="$REPO/artifacts/db/library_canonical_fresh.db"
LOG="$REPO/artifacts/logs/scan_final_library.log"
SUMMARY="$REPO/artifacts/logs/scan_final_library_summary.txt"

# Activate Python environment if needed (edit if you use a specific venv)
if [[ -f "$HOME/dedupe_repo_reclone/venv/bin/activate" ]]; then
    source "$HOME/dedupe_repo_reclone/venv/bin/activate"
fi

mkdir -p "$(dirname "$DB_OUT")"
mkdir -p "$(dirname "$LOG")"

# Remove previous DB if present
if [[ -f "$DB_OUT" ]]; then
    mv "$DB_OUT" "$DB_OUT.bak.$(date +%Y%m%d_%H%M%S)"
fi

# Run the scan using Python (verbose)
cat <<EOF > "$REPO/scan_final_library.py"
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
    print(f"[{idx}/{total}] {path}")
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
EOF

export SCAN_ROOT="$SCAN_ROOT"
export DB_OUT="$DB_OUT"

python3 "$REPO/scan_final_library.py" | tee "$LOG"

COUNT=$(sqlite3 "$DB_OUT" "SELECT COUNT(*) FROM library_files;")
echo "Total FLAC files scanned: $COUNT" | tee "$SUMMARY"

# Validate file count matches disk
DISK_COUNT=$(find "$SCAN_ROOT" -type f -name "*.flac" | wc -l)
echo "Total FLAC files on disk: $DISK_COUNT" | tee -a "$SUMMARY"

if [[ "$COUNT" -eq "$DISK_COUNT" ]]; then
    echo "✔ All files indexed correctly." | tee -a "$SUMMARY"
else
    echo "✗ Mismatch between DB and disk count!" | tee -a "$SUMMARY"
fi

echo "Scan complete. DB: $DB_OUT" | tee -a "$SUMMARY"
echo "Log: $LOG" | tee -a "$SUMMARY"
