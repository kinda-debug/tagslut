#!/usr/bin/env python3
"""Check audio fingerprinting scan progress."""

import sqlite3
from pathlib import Path


def main() -> int:
    db = Path.home() / '.cache' / 'file_dupes.db'
    if not db.exists():
        print(f"Database not found: {db}")
        return 1
    
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Total files in DB
    cur.execute("SELECT COUNT(*) FROM file_hashes")
    total = cur.fetchone()[0]

    # Files with audio fingerprints
    cur.execute(
        "SELECT COUNT(*) FROM file_hashes "
        "WHERE audio_fingerprint_hash IS NOT NULL"
    )
    with_fp = cur.fetchone()[0]

    # Files in Dupeguru folder
    cur.execute(
        "SELECT COUNT(*) FROM file_hashes WHERE file_path LIKE '%Dupeguru%'"
    )
    dupeguru_total = cur.fetchone()[0]

    # Dupeguru files with audio fingerprints
    cur.execute(
        "SELECT COUNT(*) FROM file_hashes "
        "WHERE file_path LIKE '%Dupeguru%' "
        "AND audio_fingerprint_hash IS NOT NULL"
    )
    dupeguru_with_fp = cur.fetchone()[0]

    print(f"📊 Audio Fingerprinting Progress:")
    print(f"   Total files in DB: {total:,}")
    print(f"   Files with audio fingerprints: {with_fp:,}")
    print(f"")
    print(f"   Dupeguru folder files: {dupeguru_total:,}")
    print(f"   Dupeguru files fingerprinted: {dupeguru_with_fp:,}")

    if dupeguru_total > 0:
        pct = (dupeguru_with_fp / dupeguru_total) * 100
        print(f"   Progress: {pct:.1f}%")
        
        if dupeguru_with_fp < dupeguru_total:
            remaining = dupeguru_total - dupeguru_with_fp
            print(f"   Remaining: {remaining:,} files")

    # Check for duplicate audio fingerprints
    cur.execute(
        """
        SELECT audio_fingerprint_hash, COUNT(*) as cnt
        FROM file_hashes
        WHERE audio_fingerprint_hash IS NOT NULL
        GROUP BY audio_fingerprint_hash
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 10
        """
    )

    dupes = cur.fetchall()
    if dupes:
        print(f"\n🔍 Audio Duplicate Groups Found: {len(dupes)}")
        for fp_hash, count in dupes[:5]:
            print(f"   {fp_hash[:16]}... : {count} files")
    else:
        print(f"\n✓ No audio duplicates found yet")

    conn.close()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
