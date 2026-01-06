#!/usr/bin/env python3
"""Generate duplicate clustering with filters for file size and duration."""

import sqlite3
import csv
import os

DB_PATH = 'artifacts/db/music.db'
OUTPUT_CSV = 'duplicates_clustered.csv'

# Filters
MIN_SIZE_MB = 10
MIN_DURATION_SEC = 90

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

query = """
WITH ranked AS (
  SELECT 
    path, checksum, library, zone, duration, sample_rate, bit_depth,
    ROW_NUMBER() OVER (
      PARTITION BY checksum 
      ORDER BY 
        CASE zone 
          WHEN 'accepted' THEN 1 
          WHEN 'staging' THEN 2 
          WHEN 'suspect' THEN 3 
          WHEN 'quarantine' THEN 4 
          ELSE 5 
        END,
        bit_depth DESC,
        sample_rate DESC,
        path
    ) as rank,
    COUNT(*) OVER (PARTITION BY checksum) as total_copies
  FROM files 
  WHERE checksum NOT LIKE 'NOT_SCANNED%'
    AND (duration IS NULL OR duration >= ?)
)
SELECT 
  checksum, path, library, zone, duration, sample_rate, bit_depth, 
  rank, total_copies,
  CASE WHEN rank = 1 THEN 'KEEP' ELSE 'DELETE' END as decision
FROM ranked
WHERE total_copies > 1
ORDER BY total_copies DESC, checksum, rank
"""

print(f"Filtering files >= {MIN_DURATION_SEC} seconds...")
cursor.execute(query, (MIN_DURATION_SEC,))
rows = cursor.fetchall()

with open(OUTPUT_CSV, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow([
        'checksum', 'path', 'library', 'zone', 'duration', 
        'sample_rate', 'bit_depth', 'rank', 
        'total_copies', 'decision'
    ])
    
    # Filter by file size while writing
    filtered_rows = []
    for row in rows:
        path = row[1]
        try:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb >= MIN_SIZE_MB:
                filtered_rows.append(row)
        except (OSError, FileNotFoundError):
            # File doesn't exist or can't access - skip it
            pass
    
    writer.writerows(filtered_rows)
    rows = filtered_rows  # Update for final count

keep_count = sum(1 for r in rows if r[7] == 'KEEP')
delete_count = len(rows) - keep_count

print(f"\n✓ Generated {OUTPUT_CSV}")
print(f"  Total duplicate records: {len(rows):,}")
print(f"  Files to KEEP: {keep_count:,}")
print(f"  Files to DELETE: {delete_count:,}")

conn.close()
