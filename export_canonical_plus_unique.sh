#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
SRC="$REPO/artifacts/db/library_final.db"
OUT="$REPO/artifacts/db/library_canonical_full.db"
MISSING="$REPO/artifacts/logs/canonical_full_missing.log"

echo "=== Building FULL canonical library (rank=1 + unique) ==="
echo "Source: $SRC"
echo "Output: $OUT"

rm -f "$OUT" "$MISSING"

sqlite3 "$OUT" <<'SQL'
CREATE TABLE library_files (
    path TEXT PRIMARY KEY,
    tags_json TEXT,
    extra_json TEXT
);
SQL

echo "=== Inserting duplicate-group winners ==="
sqlite3 "$OUT" <<SQL
ATTACH '$SRC' AS src;
INSERT INTO library_files (path, tags_json, extra_json)
SELECT path, tags_json, extra_json
FROM src.library_files
WHERE duplicate_rank = 1;
DETACH src;
SQL

echo "=== Inserting unique files ==="
sqlite3 "$OUT" <<SQL
ATTACH '$SRC' AS src;
INSERT INTO library_files (path, tags_json, extra_json)
SELECT path, tags_json, extra_json
FROM src.library_files
WHERE duplicate_rank IS NULL;
DETACH src;
SQL

echo "=== Verifying counts ==="
sqlite3 "$OUT" "SELECT COUNT(*) FROM library_files;"

echo "=== Checking on-disk file existence ==="
sqlite3 "$OUT" "SELECT path FROM library_files;" | while read -r p; do
    [ -f "$p" ] || echo "$p" >> "$MISSING"
done

echo "Missing file report: $MISSING"
echo "=== DONE ==="
echo "Full canonical library: $OUT"
