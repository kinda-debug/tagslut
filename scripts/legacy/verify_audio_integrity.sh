#!/usr/bin/env bash
set -e

OUTDIR="artifacts/metadata_audit"
RAW="$OUTDIR/missing_metadata_raw.txt"
LIST="$OUTDIR/missing_metadata.txt"
OK="$OUTDIR/tmp_ok.txt"
BAD="$OUTDIR/tmp_bad.txt"

mkdir -p "$OUTDIR"

echo "=== STEP 1: Extract files with missing/zero metadata ==="

sqlite3 artifacts/db/library.db <<'EOF' > "$RAW"
.headers off
.mode list
SELECT path
FROM library_files
WHERE size_bytes IS NULL
   OR size_bytes = 0
   OR mtime IS NULL
   OR duration IS NULL
   OR sample_rate IS NULL
   OR bit_rate IS NULL
   OR channels IS NULL
   OR bit_depth IS NULL;
EOF

echo "Raw list saved to: $RAW"

echo "=== STEP 2: Clean list ==="
sed 's/"//g' "$RAW" | sed '/^\s*$/d' > "$LIST"

COUNT=$(wc -l < "$LIST")
echo "Found $(printf '%8d' "$COUNT") files with missing metadata."

echo "=== STEP 3: flac --test ==="

rm -f "$OK" "$BAD"

while IFS= read -r file; do
    [ -z "$file" ] && continue

    if [ ! -f "$file" ]; then
        echo "MISSING: $file" >> "$BAD"
        continue
    fi

    flac --test "$file" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "OK: $file" >> "$OK"
    else
        echo "CORRUPT: $file" >> "$BAD"
    fi
done < "$LIST"

echo "=== STEP 4: Classify results ==="

grep "^MISSING: " "$BAD" 2>/dev/null \
    | sed 's/^MISSING: //' \
    | sed 's/^/"/; s/$/"/' \
    | awk '{print $0",file_not_found"}' \
    > "$OUTDIR/missing_files.csv"

grep "^CORRUPT: " "$BAD" 2>/dev/null \
    | sed 's/^CORRUPT: //' \
    | sed 's/^/"/; s/$/"/' \
    | awk '{print $0",corrupt_audio"}' \
    > "$OUTDIR/corrupt_audio.csv"

sed 's/^OK: //' "$OK" 2>/dev/null \
    | sed 's/^/"/; s/$/"/' \
    | awk '{print $0",ok_audio_missing_metadata"}' \
    > "$OUTDIR/ok_but_missing_metadata.csv"

echo "=== STEP 5: Combine ==="

echo "path,status" > "$OUTDIR/master_report.csv"
cat "$OUTDIR"/missing_files.csv >> "$OUTDIR/master_report.csv"
cat "$OUTDIR"/corrupt_audio.csv >> "$OUTDIR/master_report.csv"
cat "$OUTDIR"/ok_but_missing_metadata.csv >> "$OUTDIR/master_report.csv"

echo "Master report: $OUTDIR/master_report.csv"