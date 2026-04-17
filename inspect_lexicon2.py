#!/usr/bin/env python3
import sqlite3

DB = '/Volumes/MUSIC/Lexicon/Backups/main.db'
con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
cur = con.cursor()

# 1. Playlist columns
print('=== Playlist columns ===')
cur.execute('PRAGMA table_info(Playlist)')
cols = [r[1] for r in cur.fetchall()]
print(cols)
cur.execute('SELECT * FROM Playlist LIMIT 3')
for r in cur.fetchall():
    print(r)

# 2. AlbumartPreview columns + sample
print('\n=== AlbumartPreview columns ===')
cur.execute('PRAGMA table_info(AlbumartPreview)')
cols_art = [r[1] for r in cur.fetchall()]
print(cols_art)
cur.execute('SELECT COUNT(*) FROM AlbumartPreview')
print('rows:', cur.fetchone()[0])
cur.execute('SELECT * FROM AlbumartPreview LIMIT 1')
row = cur.fetchone()
if row:
    for col, val in zip(cols_art, row):
        if isinstance(val, bytes):
            print(f'  {col}: <bytes len={len(val)}>')
        else:
            print(f'  {col}: {repr(val)[:120]}')

# 3. Track.data sample
print('\n=== Track.data sample ===')
cur.execute('PRAGMA table_info(Track)')
track_cols = [r[1] for r in cur.fetchall()]
cur.execute('SELECT * FROM Track WHERE data IS NOT NULL LIMIT 1')
row = cur.fetchone()
if row:
    for col, val in zip(track_cols, row):
        if isinstance(val, bytes):
            print(f'  {col}: <bytes len={len(val)}>')
        else:
            print(f'  {col}: {repr(val)[:120]}')

con.close()
