#!/usr/bin/env python3
"""Migrate database schema to add audio fingerprint columns."""

import sqlite3
from pathlib import Path

def main() -> int:
    db = Path.home() / '.cache' / 'file_dupes.db'
    if not db.exists():
        print(f"Database not found: {db}")
        return 1
    
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Check if columns exist
    try:
        cur.execute('SELECT audio_fingerprint FROM file_hashes LIMIT 1')
        print('audio_fingerprint column already exists')
    except sqlite3.OperationalError:
        print('Adding audio_fingerprint column...')
        cur.execute('ALTER TABLE file_hashes ADD COLUMN audio_fingerprint TEXT')
        conn.commit()
        print('  ✓ Added audio_fingerprint column')

    try:
        cur.execute('SELECT audio_fingerprint_hash FROM file_hashes LIMIT 1')
        print('audio_fingerprint_hash column already exists')
    except sqlite3.OperationalError:
        print('Adding audio_fingerprint_hash column...')
        cur.execute(
            'ALTER TABLE file_hashes ADD COLUMN audio_fingerprint_hash TEXT'
        )
        conn.commit()
        print('  ✓ Added audio_fingerprint_hash column')

    # Create index
    try:
        cur.execute(
            'CREATE INDEX idx_audio_fingerprint_hash '
            'ON file_hashes(audio_fingerprint_hash)'
        )
        conn.commit()
        print('  ✓ Created index on audio_fingerprint_hash')
    except sqlite3.OperationalError as e:
        if 'already exists' in str(e):
            print('Index already exists')
        else:
            raise

    conn.close()
    print('\n✅ Database schema updated successfully')
    return 0

if __name__ == '__main__':
    import sys
    sys.exit(main())
