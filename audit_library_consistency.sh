#!/usr/bin/env bash
set -euo pipefail

DB="artifacts/db/library_final.db"
OUT_DIR="/Volumes/dotad/audit_report"

# --- Ensure output directory ---
mkdir -p "$OUT_DIR"

echo "------------------------------------------------------------"
echo "LIBRARY AUDIT"
echo "DB:         $DB"
echo "Report dir: $OUT_DIR"
echo "------------------------------------------------------------"

# --- Step 1: Export DB to TSV ---
echo "[STEP 1] Exporting DB entries to TSV …"
sqlite3 -header -separator $'\t' "$DB" \
    "SELECT * FROM library_files;" \
    > "$OUT_DIR/db_all.tsv"

cut -f1 "$OUT_DIR/db_all.tsv" | sort -u > "$OUT_DIR/db_paths.txt"
DB_COUNT=$(wc -l < "$OUT_DIR/db_paths.txt")
echo "  - DB rows exported: $DB_COUNT"

# --- Step 2: Scan filesystem for FLACs ---
echo "------------------------------------------------------------"
echo "[STEP 2] Scanning filesystem for FLAC files …"

FLAC_RAW="$OUT_DIR/fs_all_flac_raw.txt"
FLAC_NORM="$OUT_DIR/fs_all_flac.txt"

find /Volumes/dotad/MUSIC \
     /Volumes/dotad/NEW_MUSIC \
     /Volumes/dotad/NEW_LIBRARY \
     /Volumes/dotad/QUARANTINE_AUTO_GLOBAL \
     -type f -iname '*.flac' \
     | sort > "$FLAC_RAW"

# Normalise paths
python3 <<'EOF' > "$FLAC_NORM"
import sys, unicodedata
def norm(p): return unicodedata.normalize("NFC", p.strip())
print("\n".join(norm(l) for l in sys.stdin))
EOF
< "$FLAC_RAW"

FS_COUNT=$(wc -l < "$FLAC_NORM")
echo "  - Normalised unique FS FLAC: $FS_COUNT"

# --- Step 3: Compare DB vs FS ---
echo "------------------------------------------------------------"
echo "[STEP 3] Comparing DB paths vs filesystem paths …"

comm -23 "$OUT_DIR/db_paths.txt" "$FLAC_NORM" > "$OUT_DIR/missing_on_disk_by_comm.txt"
comm -13 "$OUT_DIR/db_paths.txt" "$FLAC_NORM" > "$OUT_DIR/missing_in_db.txt"

MIS_COMM=$(wc -l < "$OUT_DIR/missing_on_disk_by_comm.txt")
MIS_DB=$(wc -l < "$OUT_DIR/missing_in_db.txt")

echo "  - DB paths missing on disk (comm): $MIS_COMM"
echo "  - FS paths missing in DB: $MIS_DB"

# --- Step 4: Strict check ---
echo "------------------------------------------------------------"
echo "[STEP 4] Strict disk existence & size verification …"

STRICT_MISSING="$OUT_DIR/missing_on_disk_strict.txt"
SIZE_MISMATCH="$OUT_DIR/size_mismatches.txt"

> "$STRICT_MISSING"
> "$SIZE_MISMATCH"

while IFS= read -r p; do
    if [[ ! -f "$p" ]]; then
        echo "$p" >> "$STRICT_MISSING"
        continue
    fi
    # Retrieve size from DB
    DB_SIZE=$(sqlite3 "$DB" "SELECT size_bytes FROM library_files WHERE path='$p';")
    FS_SIZE=$(stat -f%z "$p" || echo 0)
    if [[ "$FS_SIZE" != "$DB_SIZE" ]]; then
        echo -e "$p\tDB:$DB_SIZE\tFS:$FS_SIZE" >> "$SIZE_MISMATCH"
    fi
done < "$OUT_DIR/db_paths.txt"

STRICT_COUNT=$(wc -l < "$STRICT_MISSING")
SIZE_COUNT=$(wc -l < "$SIZE_MISMATCH")

echo "  - Missing on disk (strict): $STRICT_COUNT"
echo "  - Size mismatches: $SIZE_COUNT"

# --- Step 5: MD5 duplicate analysis ---
echo "------------------------------------------------------------"
echo "[STEP 5] MD5 duplicate analysis …"

DUP_GROUPS="$OUT_DIR/md5_duplicate_groups.txt"
DUP_ROWS="$OUT_DIR/md5_duplicates.tsv"

sqlite3 -header -separator $'\t' "$DB" \
"
SELECT fingerprint, COUNT(*) AS cnt
FROM library_files
WHERE fingerprint IS NOT NULL
GROUP BY fingerprint
HAVING cnt > 1
ORDER BY cnt DESC;
" > "$DUP_GROUPS"

sqlite3 -header -separator $'\t' "$DB" \
"
SELECT *
FROM library_files
WHERE fingerprint IN (
    SELECT fingerprint
    FROM library_files
    WHERE fingerprint IS NOT NULL
    GROUP BY fingerprint
    HAVING COUNT(*) > 1
);
" > "$DUP_ROWS"

echo "  - Duplicate checksum groups: $(wc -l < "$DUP_GROUPS")"
echo "  - Duplicate checksum rows: $(wc -l < "$DUP_ROWS")"

# --- Step 6: Summary ---
echo "------------------------------------------------------------"
echo "[STEP 6] Summary written to $OUT_DIR/summary.txt"
echo "------------------------------------------------------------"

{
    echo "LIBRARY AUDIT SUMMARY"
    echo "======================"
    echo ""
    echo "DB path:              $DB"
    echo "Report directory:     $OUT_DIR"
    echo ""
    echo "COUNTS"
    echo "------"
    echo "DB rows:                        $DB_COUNT"
    echo "Normalised FS FLAC count:       $FS_COUNT"
    echo ""
    echo "MISSING / EXTRA"
    echo "---------------"
    echo "DB missing (comm):              $MIS_COMM"
    echo "Missing in DB:                  $MIS_DB"
    echo "Strict missing:                 $STRICT_COUNT"
    echo "Size mismatches:                $SIZE_COUNT"
} > "$OUT_DIR/summary.txt"

echo "AUDIT COMPLETE."
