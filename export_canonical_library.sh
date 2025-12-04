#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
SRC_DB="$REPO/artifacts/db/library_final.db"
OUT_DB="$REPO/artifacts/db/library_canonical_export.db"
TMPDB="$OUT_DB.tmp"

echo "=== Building canonical export ==="
echo "Source DB: $SRC_DB"
echo "Output DB: $OUT_DB"
echo

# Remove any previous temp
rm -f "$TMPDB"

# Create schema
sqlite3 "$TMPDB" << 'SQL'
CREATE TABLE canonical_tracks (
    path TEXT PRIMARY KEY,
    checksum TEXT,
    duration REAL,
    size_bytes INTEGER,
    sample_rate INTEGER,
    bit_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    tags_json TEXT,
    extra_json TEXT
);
SQL

echo "=== Selecting canonical rows ==="

sqlite3 "$TMPDB" <<SQL
ATTACH '$SRC_DB' AS src;

INSERT INTO canonical_tracks
SELECT
    path,
    checksum,
    duration,
    size_bytes,
    sample_rate,
    bit_rate,
    channels,
    bit_depth,
    tags_json,
    extra_json
FROM src.library_files
WHERE duplicate_rank = 1
  AND path IS NOT NULL
  AND checksum IS NOT NULL;

DETACH src;
SQL

echo "=== Verifying export ==="
sqlite3 "$TMPDB" "SELECT COUNT(*) AS canonical_count FROM canonical_tracks;"

echo "=== Checking on-disk existence ==="
sqlite3 "$TMPDB" "SELECT path FROM canonical_tracks;" | while read -r p; do
    [[ -f "$p" ]] || echo "MISSING: $p"
done > "$REPO/artifacts/logs/canonical_missing_paths.log" || true

echo "Missing file report: artifacts/logs/canonical_missing_paths.log"
echo

echo "=== Finalizing ==="
mv "$TMPDB" "$OUT_DB"
echo "Canonical export ready:"
echo "$OUT_DB"
