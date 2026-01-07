import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

try:
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path
except ModuleNotFoundError:  # pragma: no cover
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))
    from dedupe.utils.config import get_config
    from dedupe.utils.db import open_db, resolve_db_path

parser = argparse.ArgumentParser(description="Scan a library and populate a minimal library_files table.")
parser.add_argument("--scan-root", required=True, help="Root directory to scan")
parser.add_argument("--db", required=False, type=Path, help="Output SQLite DB path")
parser.add_argument("--progress-file", default="scan_progress.txt", help="Progress checkpoint file")
parser.add_argument("--create-db", action="store_true", help="Allow creating a new DB file")
parser.add_argument("--allow-repo-db", action="store_true", help="Allow repo-local DB paths")
args = parser.parse_args()

repo_root = Path(__file__).resolve().parents[2]
resolution = resolve_db_path(
    args.db,
    config=get_config(),
    allow_repo_db=args.allow_repo_db,
    repo_root=repo_root,
    purpose="write",
    allow_create=args.create_db,
)

SCAN_ROOT = args.scan_root
PROGRESS_FILE = args.progress_file
conn = open_db(resolution)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS library_files (
    path TEXT PRIMARY KEY,
    checksum TEXT,
    duration REAL,
    artist TEXT,
    album TEXT,
    title TEXT,
    mtime REAL
)''')
conn.commit()
# Ensure mtime column exists if upgrading from old DB
def ensure_mtime_column():
    c.execute("PRAGMA table_info(library_files)")
    columns = [row[1] for row in c.fetchall()]
    if 'mtime' not in columns:
        print("[INFO] Adding mtime column to existing library_files table...")
        c.execute("ALTER TABLE library_files ADD COLUMN mtime REAL")
        conn.commit()
ensure_mtime_column()

flac_files = list(Path(SCAN_ROOT).rglob('*.flac'))
total = len(flac_files)
print(f"Scanning {total} FLAC files in {SCAN_ROOT}...\n")
start_idx = 0
if os.path.exists(PROGRESS_FILE):
    try:
        with open(PROGRESS_FILE, 'r') as pf:
            start_idx = int(pf.read().strip())
        print(f"Resuming scan from file index {start_idx+1} of {total}...")
    except Exception as e:
        print(f"[WARN] Could not read progress file: {e}")
        start_idx = 0
else:
    print(f"Starting scan from beginning...")
for idx, fpath in enumerate(flac_files, 1):
    path = str(fpath)
    if idx <= start_idx:
        continue
    try:
        mtime = os.path.getmtime(path)
        c.execute('SELECT checksum, mtime FROM library_files WHERE path=?', (path,))
        row = c.fetchone()
        if row:
            db_checksum, db_mtime = row
            if db_mtime == mtime:
                print(f"[{idx}/{total}] SKIP (already indexed, unchanged mtime): {path}")
                continue
            else:
                print(f"[{idx}/{total}] REPROCESS (mtime changed): {path}")
        else:
            print(f"[{idx}/{total}] NEW: {path}")
        # Calculate checksum
        try:
            with open(path, 'rb') as f:
                checksum = hashlib.sha256(f.read()).hexdigest()
        except PermissionError as e:
            print(f"  [ERROR] Permission denied: {path} -- Skipping.")
            checksum = None
            duration = None
            artist = album = title = None
            # Update progress file after each file
            try:
                with open(PROGRESS_FILE, 'w') as pf:
                    pf.write(str(idx))
            except Exception as e:
                print(f"[WARN] Could not update progress file: {e}")
            continue
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
        c.execute('INSERT OR REPLACE INTO library_files VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (path, checksum, duration, artist, album, title, mtime))
        conn.commit()
        # Update progress file after each file
        try:
            with open(PROGRESS_FILE, 'w') as pf:
                pf.write(str(idx))
        except Exception as e:
            print(f"[WARN] Could not update progress file: {e}")
    except Exception as e:
        print(f"  [ERROR] Unexpected error for {path}: {e} -- Skipping.")
        # Update progress file after each file
        try:
            with open(PROGRESS_FILE, 'w') as pf:
                pf.write(str(idx))
        except Exception as e:
            print(f"[WARN] Could not update progress file: {e}")
        continue
conn.close()
print("\nScan complete.")
if os.path.exists(PROGRESS_FILE):
    try:
        os.remove(PROGRESS_FILE)
    except Exception as e:
        print(f"[WARN] Could not remove progress file: {e}")
