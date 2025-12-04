#!/usr/bin/env bash
set -euo pipefail

REPO="$HOME/dedupe_repo_reclone"
SRC_DB="$REPO/artifacts/db/library_canonical_full.db"
DEST_ROOT="/Volumes/bad/FINAL_LIBRARY"
LIST="$REPO/artifacts/logs/canonical_paths.txt"
LOG="$REPO/artifacts/logs/finalize_moves.log"

echo "=== FINALIZE LIBRARY: MOVE CANONICAL FILES TO $DEST_ROOT ==="

mkdir -p "$DEST_ROOT"
mkdir -p "$(dirname "$LIST")"
mkdir -p "$(dirname "$LOG")"

echo
echo "=== STEP 1: Extract canonical paths ==="
sqlite3 "$SRC_DB" "
    SELECT path
    FROM library_files
    WHERE path LIKE '/Volumes/dotad/%';
" > "$LIST"

COUNT=$(wc -l < "$LIST" | tr -d ' ')
echo "Found canonical FLAC paths: $COUNT"
echo "List saved to: $LIST"

echo
echo "=== STEP 2: Move files to $DEST_ROOT ==="
echo "Logging moves to: $LOG"

while IFS= read -r src; do
    [[ -z "$src" ]] && continue

    rel="${src#/Volumes/dotad/}"
    dest="$DEST_ROOT/$rel"
    dest_dir="$(dirname "$dest")"

    mkdir -p "$dest_dir"

    if [[ -f "$dest" ]]; then
        echo "SKIP (exists): $rel"
        continue
    fi

    if [[ -f "$src" ]]; then
        echo "MOVE: $src"
        echo "MOVE: $src -> $dest" >> "$LOG"
        mv "$src" "$dest"
    else
        echo "MISSING: $src"
        echo "MISSING: $src" >> "$LOG"
    fi

done < "$LIST"

echo
echo "=== DONE ==="
echo "Canonical library completed at:"
echo "    $DEST_ROOT"
echo "Move log:"
echo "    $LOG"
