#!/usr/bin/env bash
set -euo pipefail

LIB_DB="artifacts/db/library.db"
REC_DB="artifacts/db/recovered.db"
MANIFEST="artifacts/reports/manifest.csv"
CLEAN="artifacts/reports/manifest.cleaned.csv"
TMPDB="/tmp/verify_manifest.db"
TMPCSV="/tmp/manifest_no_header.csv"

echo "=== VERIFYING MANIFEST ==="

rm -f "$TMPDB" "$TMPCSV"

# Extract header + data
HEADER=$(head -n 1 "$MANIFEST")
tail -n +2 "$MANIFEST" > "$TMPCSV"

# Create DB and table
sqlite3 "$TMPDB" <<SQL
CREATE TABLE manifest (
    library_path TEXT,
    recovered_path TEXT,
    similarity REAL,
    reason TEXT
);
SQL

echo "[0/5] Importing manifest (skipping header)..."
sqlite3 "$TMPDB" <<SQL
.mode csv
.import '$TMPCSV' manifest
SQL

echo "[1/5] Checking that all library paths exist..."
sqlite3 "$TMPDB" <<SQL > /tmp/missing_lib.txt
ATTACH '$LIB_DB' AS ldb;
SELECT m.library_path
FROM manifest AS m
LEFT JOIN ldb.library_files AS l ON l.path = m.library_path
WHERE l.path IS NULL;
SQL

if [[ -s /tmp/missing_lib.txt ]]; then
    echo "ERROR: Missing library paths:"
    cat /tmp/missing_lib.txt
    exit 1
fi
echo "✓ All library paths valid."


echo "[2/5] Checking recovered paths..."
sqlite3 "$TMPDB" <<SQL > /tmp/missing_rec.txt
ATTACH '$REC_DB' AS rdb;
SELECT m.recovered_path
FROM manifest AS m
LEFT JOIN rdb.recovered_files AS r ON r.source_path = m.recovered_path
WHERE r.source_path IS NULL;
SQL

if [[ -s /tmp/missing_rec.txt ]]; then
    echo "ERROR: Missing recovered paths:"
    cat /tmp/missing_rec.txt
    exit 1
fi
echo "✓ All recovered paths valid."


echo "[3/5] Checking size safety..."
sqlite3 "$TMPDB" <<SQL > /tmp/size_errors.txt
ATTACH '$LIB_DB' AS ldb;
ATTACH '$REC_DB' AS rdb;
SELECT m.library_path, m.recovered_path, l.size_bytes, r.size_bytes
FROM manifest AS m
JOIN ldb.library_files AS l ON l.path = m.library_path
JOIN rdb.recovered_files AS r ON r.source_path = m.recovered_path
WHERE r.size_bytes < l.size_bytes;
SQL

if [[ -s /tmp/size_errors.txt ]]; then
    echo "ERROR: Size violations:"
    cat /tmp/size_errors.txt
    exit 1
fi
echo "✓ All size relationships safe."


echo "[4/5] Checking for duplicate recovered targets..."
sqlite3 "$TMPDB" <<SQL > /tmp/dup_rec.txt
SELECT recovered_path, COUNT(*)
FROM manifest
GROUP BY recovered_path
HAVING COUNT(*) > 1;
SQL

if [[ -s /tmp/dup_rec.txt ]]; then
    echo "ERROR: Duplicate recovered targets:"
    cat /tmp/dup_rec.txt
    exit 1
fi
echo "✓ No duplicated recovered paths."


echo "[5/5] Writing cleaned manifest..."
echo "$HEADER" > "$CLEAN"
cat "$TMPCSV" >> "$CLEAN"

echo "✓ Clean manifest written to $CLEAN"
echo "=== VERIFY COMPLETE ==="
