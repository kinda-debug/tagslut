#!/usr/bin/env bash
set -euo pipefail
set -x

REPO="$HOME/dedupe_repo_reclone"
FINAL_DB="$REPO/artifacts/db/library_final.db"
TMP_DB="$FINAL_DB.tmp"

# Step 1: Backup broken DB if present
if [[ -f "$FINAL_DB" ]]; then
    mv "$FINAL_DB" "$REPO/artifacts/db/library_final.broken.db"
fi

# Step 2: Activate environment
if [[ -f "$REPO/.venv/bin/activate" ]]; then
    source "$REPO/.venv/bin/activate"
fi

echo "=== RESETTING TEMPORARY FINAL DB ==="
rm -f "$TMP_DB"

# Step 3: Create full schema and merge all fields from scan DBs
sqlite3 "$TMP_DB" <<'SQL'
CREATE TABLE library_files (
    path TEXT PRIMARY KEY,
    size_bytes INTEGER,
    mtime REAL,
    checksum TEXT,
    duration REAL,
    sample_rate INTEGER,
    bit_rate INTEGER,
    channels INTEGER,
    bit_depth INTEGER,
    tags_json TEXT,
    fingerprint TEXT,
    fingerprint_duration REAL,
    dup_group TEXT,
    duplicate_rank INTEGER,
    is_canonical INTEGER,
    extra_json TEXT
);
SQL

echo
for db in "$REPO"/artifacts/db/rescan/*.sqlite; do
    echo "Merging $db"
    sqlite3 "$TMP_DB" <<SQL
ATTACH '$db' AS scan;
INSERT OR REPLACE INTO library_files
SELECT
    path,
    size_bytes,
    mtime,
    checksum,
    duration,
    sample_rate,
    bit_rate,
    channels,
    bit_depth,
    tags_json,
    fingerprint,
    fingerprint_duration,
    dup_group,
    duplicate_rank,
    is_canonical,
    extra_json
FROM scan.library_files;
DETACH scan;
SQL
    echo
done

# Step 4: Basic stats
sqlite3 "$TMP_DB" "SELECT COUNT(*) AS total_files FROM library_files;"
sqlite3 "$TMP_DB" "SELECT COUNT(*) AS missing_checksum FROM library_files WHERE checksum IS NULL OR checksum = '';"
sqlite3 "$TMP_DB" "SELECT COUNT(*) AS missing_size_bytes FROM library_files WHERE size_bytes IS NULL OR size_bytes = 0;"

# Step 5: Create canonical table
sqlite3 "$TMP_DB" <<'SQL'
DROP TABLE IF EXISTS canonical;
CREATE TABLE canonical AS
SELECT * FROM library_files WHERE (checksum, duration, bit_rate, size_bytes) IN (
    SELECT checksum,
           MAX(duration),
           MAX(bit_rate),
           MAX(size_bytes)
    FROM library_files
    WHERE checksum IS NOT NULL AND checksum != ''
    GROUP BY checksum
);
SQL

# Step 6: Generate dedupe plan
sqlite3 "$TMP_DB" <<'SQL' > "$REPO/artifacts/db/dedupe_plan.txt"
SELECT path
FROM library_files
WHERE checksum IN (SELECT checksum FROM canonical)
AND path NOT IN (SELECT path FROM canonical);
SQL

wc -l "$REPO/artifacts/db/dedupe_plan.txt"

# Step 7: Move non-canonical duplicates to quarantine
TS=$(date +"%Y%m%d_%H%M%S")
QUAR="/Volumes/dotad/DEDUPER_QUARANTINE_$TS"
mkdir -p "$QUAR"

echo "Moving non-canonical duplicates to quarantine: $QUAR"
moved=0
failed=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if [[ -f "$f" ]]; then
        dest="$QUAR/$(basename "$f")"
        mv "$f" "$dest" && moved=$((moved+1)) || failed=$((failed+1))
    else
        echo "Missing file on disk: $f"
        failed=$((failed+1))
    fi
done < "$REPO/artifacts/db/dedupe_plan.txt"

echo "=== DEDUPE MOVE COMPLETE ==="
echo "Moved:   $moved"
echo "Failed:  $failed"
echo "Quarantined into: $QUAR"
echo "Plan file: $REPO/artifacts/db/dedupe_plan.txt"

echo "=== FINALIZING LIBRARY DB ==="
mv "$TMP_DB" "$FINAL_DB"
echo "Final library DB: $FINAL_DB"
