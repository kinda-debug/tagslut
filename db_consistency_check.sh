#!/usr/bin/env bash
set -euo pipefail

echo "=== CROSS-DB CONSISTENCY CHECK ==="

LIB="artifacts/db/library.db"
REC="artifacts/db/recovered.db"

echo "-- Checking core tables"
sqlite3 "$LIB" ".schema library_files" >/dev/null || { echo "library_files missing"; exit 1; }
sqlite3 "$REC" ".schema recovered_files" >/dev/null || { echo "recovered_files missing"; exit 1; }
echo "✓ Schemas exist"

echo "-- Checking for NULL paths in library"
sqlite3 "$LIB" "SELECT COUNT(*) FROM library_files WHERE path IS NULL;" | \
    awk '{print "NULL paths in library_files:", $1}'

echo "-- Checking for NULL source_path in recovered"
sqlite3 "$REC" "SELECT COUNT(*) FROM recovered_files WHERE source_path IS NULL;" | \
    awk '{print "NULL source_path in recovered_files:", $1}'

echo "-- Checking for duplicate paths"
sqlite3 "$LIB" "SELECT path, COUNT(*) FROM library_files GROUP BY path HAVING COUNT(*)>1;" > /tmp/lib_dupes.txt
sqlite3 "$REC" "SELECT source_path, COUNT(*) FROM recovered_files GROUP BY source_path HAVING COUNT(*)>1;" > /tmp/rec_dupes.txt

if [[ -s /tmp/lib_dupes.txt ]]; then
    echo "!! DUPLICATE library paths:"
    cat /tmp/lib_dupes.txt
else
    echo "✓ No duplicate library paths"
fi

if [[ -s /tmp/rec_dupes.txt ]]; then
    echo "!! DUPLICATE recovered paths:"
    cat /tmp/rec_dupes.txt
else
    echo "✓ No duplicate recovered paths"
fi

echo "=== CONSISTENCY CHECK COMPLETE ==="
