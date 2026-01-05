#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
# Use the fresh canonical DB (contains `library_files`) for finalization
SRC_DB="$REPO/artifacts/db/library_canonical_fresh.db"
DEST_ROOT="/Volumes/COMMUNE/20_ACCEPTED"
LIST="$REPO/artifacts/logs/canonical_paths.txt"
LOG="$REPO/artifacts/logs/finalize_moves.log"

echo "=== FINALIZE LIBRARY: MOVE CANONICAL FILES TO $DEST_ROOT ==="

mkdir -p "$DEST_ROOT"
mkdir -p "$(dirname "$LIST")"
mkdir -p "$(dirname "$LOG")"

echo
echo "=== STEP 1: Extract canonical paths ==="
# Prefer `canonical` table if present, otherwise use `library_files`
HAS_CANONICAL=$(sqlite3 "$SRC_DB" "SELECT name FROM sqlite_master WHERE type='table' AND name='canonical';")
if [[ -n "$HAS_CANONICAL" ]]; then
    SQL_SELECT="SELECT path, IFNULL(checksum, '') FROM canonical;"
else
    SQL_SELECT="SELECT path, IFNULL(checksum, '') FROM library_files;"
fi

# Prepare list and checksum mapping
rm -f "$LIST"
CHECKSUMS_FILE="$(mktemp)"
while IFS='|' read -r path checksum; do
    # Normalize commas to underscores to match helper's output
    src_esc=$(printf '%s' "$path" | sed 's/,/_/g')
    echo "$src_esc" >> "$LIST"
    echo "$src_esc,$checksum" >> "$CHECKSUMS_FILE"
done < <(sqlite3 -separator '|' "$SRC_DB" "$SQL_SELECT")

COUNT=$(wc -l < "$LIST" | tr -d ' ')
echo "Found canonical FLAC paths: $COUNT"
echo "List saved to: $LIST"

echo
echo "=== STEP 2: Move files to $DEST_ROOT ==="
echo "Logging moves to: $LOG"

MAPS_FILE="$(mktemp)"
FINAL_MAPS_FILE="$(mktemp)"
echo "Building canonical mapping using picard path builder..."
"$REPO/.venv/bin/python3" "$REPO/tools/finalize_picard_map.py" --dest-root "$DEST_ROOT" < "$LIST" > "$MAPS_FILE"

DRY_RUN=${DRY_RUN:-1}
if [[ "$DRY_RUN" -ne 0 ]]; then
  echo "DRY RUN mode enabled (no files will be moved). Set DRY_RUN=0 to perform moves.)"
fi

# Join maps with checksums into CSV: src,dest,checksum
awk -F, 'NR==FNR{chk[$1]=$2; next} {print $1","$2","(chk[$1]?chk[$1]:"")}' "$CHECKSUMS_FILE" "$MAPS_FILE" > "$FINAL_MAPS_FILE"

# Produce collision report using Python
COLLISION_REPORT="artifacts/reports/finalize_collision_report.csv"
mkdir -p "$(dirname "$COLLISION_REPORT")"
python3 - <<PY
import csv
from collections import defaultdict
infile = "$FINAL_MAPS_FILE"
out = "$COLLISION_REPORT"
dest_map = defaultdict(lambda: defaultdict(list))
with open(infile, newline='') as f:
    r = csv.reader(f)
    for row in r:
        if not row: continue
        src, dest = row[0], row[1]
        chk = row[2] if len(row) > 2 else ''
        dest_map[dest][chk].append(src)

with open(out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(["dest","checksum_count","checksums","srcs_sample"])
    for dest, chkmap in dest_map.items():
        uniq_chks = [k for k in chkmap.keys() if k]
        if len(uniq_chks) > 1:
            checks = ";".join(uniq_chks)
            # sample one src per checksum
            srcs = [ (k+":"+ (chkmap[k][0] if chkmap[k] else '')) for k in uniq_chks ]
            w.writerow([dest, len(uniq_chks), checks, " | ".join(srcs)])
PY

echo "Mapping and collision report generated: $FINAL_MAPS_FILE, $COLLISION_REPORT"

while IFS=, read -r src dest checksum; do
    [[ -z "$src" ]] && continue

    dest_dir="$(dirname "$dest")"
    mkdir -p "$dest_dir"

    if [[ -f "$dest" ]]; then
        echo "SKIP (exists): $dest"
        echo "SKIP (exists): $src -> $dest" >> "$LOG"
        continue
    fi

    if [[ -f "$src" ]]; then
        if [[ "$DRY_RUN" -ne 0 ]]; then
            echo "PLAN: $src -> $dest"
            echo "PLAN: $src -> $dest (checksum: $checksum)" >> "$LOG"
        else
            echo "MOVE: $src -> $dest"
            echo "MOVE: $src -> $dest (checksum: $checksum)" >> "$LOG"
            mv "$src" "$dest"
        fi
    else
        echo "MISSING: $src"
        echo "MISSING: $src" >> "$LOG"
    fi

done < "$FINAL_MAPS_FILE"

rm -f "$MAPS_FILE" "$CHECKSUMS_FILE" "$FINAL_MAPS_FILE"

echo
echo "=== DONE ==="
echo "Canonical library completed at:"
echo "    $DEST_ROOT"
echo "Move log:"
echo "    $LOG"
