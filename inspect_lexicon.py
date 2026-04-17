#!/usr/bin/env python3
import sqlite3
import os

dbs = [
    '/Volumes/MUSIC/Lexicon/Backups/main.db',
    '/Volumes/MUSIC/Lexicon/Backups/main 2.db',
    '/Volumes/MUSIC/Lexicon/Backups/main 3.db',
]

for db_path in dbs:
    if not os.path.exists(db_path):
        print(f'MISSING: {db_path}')
        continue
    print(f'\n=== {os.path.basename(db_path)} ({os.path.getsize(db_path)//1024//1024}MB) ===')
    try:
        con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [r[0] for r in cur.fetchall()]
        print('Tables:', tables)

        # Look for tracks/songs table and check columns
        for t in tables:
            if any(x in t.lower() for x in ['track', 'song', 'file', 'media', 'artwork', 'image']):
                cur.execute(f'PRAGMA table_info({t})')
                cols = [r[1] for r in cur.fetchall()]
                cur.execute(f'SELECT COUNT(*) FROM {t}')
                count = cur.fetchone()[0]
                print(f'  {t} ({count} rows): {cols}')
        con.close()
    except Exception as e:
        print(f'  ERROR: {e}')
