#!/usr/bin/env python3
"""Find cross-folder MD5 duplicates for Garbage/Dupeguru."""

import sqlite3
from pathlib import Path


def main() -> int:
    db = Path.home() / '.cache' / 'file_dupes.db'
    conn = sqlite3.connect(db)
    cur = conn.cursor()

    # Files in Garbage Dupeguru folder now
    cur.execute(
        """
        SELECT COUNT(*) 
        FROM file_hashes 
        WHERE file_path LIKE '%/Garbage/newgarbage/Dupeguru/%'
        """
    )
    in_db = cur.fetchone()[0]
    print(f"Files from Garbage/Dupeguru in database: {in_db}")

    # MD5 duplicates where at least one is in Garbage/Dupeguru
    # and at least one is OUTSIDE Garbage/Dupeguru
    cur.execute(
        """
        SELECT file_md5, COUNT(*) as total_files,
               SUM(CASE WHEN file_path LIKE '%/Garbage/newgarbage/Dupeguru/%' 
                   THEN 1 ELSE 0 END) as garbage_count,
               SUM(CASE WHEN file_path NOT LIKE '%/Garbage/newgarbage/Dupeguru/%' 
                   THEN 1 ELSE 0 END) as other_count
        FROM file_hashes
        WHERE file_md5 IN (
            SELECT file_md5 
            FROM file_hashes 
            WHERE file_path LIKE '%/Garbage/newgarbage/Dupeguru/%'
        )
        GROUP BY file_md5
        HAVING total_files > 1 AND other_count > 0
        ORDER BY total_files DESC
        """
    )

    cross_dupes = cur.fetchall()
    print(
        f"\nCross-folder MD5 duplicates "
        f"(Garbage/Dupeguru vs other folders): {len(cross_dupes)}"
    )

    if cross_dupes:
        total_garbage_dupes = sum(row[2] for row in cross_dupes)
        print(
            f"Total Garbage/Dupeguru files that are duplicates: "
            f"{total_garbage_dupes}"
        )
        print("\nTop 10 duplicate groups:")
        for md5, total, garbage_cnt, other_cnt in cross_dupes[:10]:
            print(
                f"  {md5[:16]}... : {total} files "
                f"({garbage_cnt} in Garbage, {other_cnt} elsewhere)"
            )
    
    conn.close()
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
