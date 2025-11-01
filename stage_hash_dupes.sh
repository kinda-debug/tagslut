#!/usr/bin/env bash
set -Eeuo pipefail

# Stage surplus duplicate files (same audiohash) into a timestamped trash under MUSIC_ROOT.
# Keeps one deterministic "keeper" per hash (lexicographically smallest path under MUSIC_ROOT).
#
# Usage:
#   stage_hash_dupes.sh [DB] [MUSIC_ROOT] [BATCH=25] [APPLY=false]
#
# Examples:
#   stage_hash_dupes.sh "$HOME/.cache/music_index_final2.db" "/Volumes/dotad/MUSIC" 15 true

DB="${1:-$HOME/.cache/music_index_final2.db}"
MUSIC_ROOT="${2:-/Volumes/dotad/MUSIC}"
BATCH="${3:-25}"
APPLY="${4:-false}"

# --- validation ---
if ! command -v sqlite3 >/dev/null 2>&1; then
  echo "sqlite3 not found in PATH." >&2; exit 1
fi
if [ ! -f "$DB" ]; then
  echo "DB not found: $DB" >&2; exit 1
fi
if [ ! -d "$MUSIC_ROOT" ]; then
  echo "MUSIC root not found: $MUSIC_ROOT" >&2; exit 1
fi

# Ensure MUSIC_ROOT has no trailing slash (normalize)
MUSIC_ROOT="${MUSIC_ROOT%/}"

TS="$(date +"%Y%m%d_%H%M%S")"
RUN_DIR="$HOME/dedupe/runs/$TS"
TRASH="$MUSIC_ROOT/_TRASH_HASH_DUPES_$TS"
mkdir -p "$RUN_DIR"

# --- build the surplus list (TSV: hash<TAB>path) ---
# Restrict to files under MUSIC_ROOT. Choose keeper = MIN(path) per hash (deterministic).
sqlite3 "$DB" > "$RUN_DIR/surplus_all.tsv" <<SQL
WITH d AS (
  SELECT audiohash
  FROM files
  WHERE audiohash IS NOT NULL
    AND path LIKE '$MUSIC_ROOT/%'
  GROUP BY audiohash
  HAVING COUNT(*) > 1
),
k AS (
  SELECT audiohash, MIN(path) AS keep_path
  FROM files
  WHERE audiohash IN d
    AND path LIKE '$MUSIC_ROOT/%'
  GROUP BY audiohash
),
s AS (
  SELECT f.audiohash AS h, f.path AS p
  FROM files f
  JOIN d ON d.audiohash = f.audiohash
  JOIN k ON k.audiohash = f.audiohash
  WHERE f.path <> k.keep_path
    AND f.path LIKE '$MUSIC_ROOT/%'
)
SELECT h || CHAR(9) || p
FROM s
ORDER BY h, p;
SQL

# Limit to first N hashes for this batch
cut -f1 "$RUN_DIR/surplus_all.tsv" | uniq > "$RUN_DIR/all_hashes.txt"
head -n "$BATCH" "$RUN_DIR/all_hashes.txt" > "$RUN_DIR/batch_hashes.txt"
grep -F -f "$RUN_DIR/batch_hashes.txt" "$RUN_DIR/surplus_all.tsv" > "$RUN_DIR/surplus_batch.tsv" || true

BATCH_HASHES=$(wc -l < "$RUN_DIR/batch_hashes.txt" | tr -d ' ')
BATCH_FILES=$( [ -s "$RUN_DIR/surplus_batch.tsv" ] && wc -l < "$RUN_DIR/surplus_batch.tsv" | tr -d ' ' || echo 0 )

echo "Run dir:                $RUN_DIR"
echo "DB:                     $DB"
echo "MUSIC root:             $MUSIC_ROOT"
echo "Planned trash staging:  $TRASH"
echo "Batch hashes:           $BATCH_HASHES"
echo "Batch surplus files:    $BATCH_FILES"
echo "Apply:                  $APPLY"

# Quick byte-size estimate of this batch
if [ -s "$RUN_DIR/surplus_batch.tsv" ]; then
  bytes=$(awk -F'\t' '{print $2}' "$RUN_DIR/surplus_batch.tsv" | while IFS= read -r p; do [ -e "$p" ] && stat -f%z "$p" || echo 0; done | awk '{s+=$1} END{print s+0}')
  gib=$(awk -v b="${bytes:-0}" 'BEGIN{printf "%.2f", b/1024/1024/1024}')
  echo "Estimated batch size:   ${bytes:-0} bytes (~${gib} GiB)"
fi

[ "$APPLY" = "true" ] || { echo "Dry-run only. To apply: $0 \"$DB\" \"$MUSIC_ROOT\" \"$BATCH\" true"; exit 0; }

mkdir -p "$TRASH"

# Collision-safe move: if destination exists, append .dupN before extension.
collision_safe_move() {
  src="$1"
  dest="$2"
  if [ ! -e "$dest" ]; then
    mv -n "$src" "$dest"
    return
  fi
  dir="$(dirname "$dest")"
  file="$(basename "$dest")"
  base="${file%.*}"
  ext="${file##*.}"
  if [ "$base" = "$file" ]; then
    # No extension
    base="$file"; ext=""
  fi
  n=1
  while :; do
    if [ -n "$ext" ]; then
      cand="$dir/${base}.dup${n}.$ext"
    else
      cand="$dir/${base}.dup${n}"
    fi
    if [ ! -e "$cand" ]; then
      mv -n "$src" "$cand"
      return
    fi
    n=$((n+1))
  done
}

# Execute moves
moved=0
failed=0
while IFS=$'\t' read -r _hash src; do
  [ -n "$src" ] || continue
  # Safety: ensure src is under MUSIC_ROOT
  case "$src" in
    "$MUSIC_ROOT"/*) ;;
    *) echo "Skip (outside MUSIC_ROOT): $src" >&2; continue ;;
  esac
  [ -e "$src" ] || { echo "Skip (missing): $src" >&2; failed=$((failed+1)); continue; }

  rel="${src#${MUSIC_ROOT}/}"
  dest="$TRASH/$rel"
  mkdir -p "$(dirname "$dest")"
  if collision_safe_move "$src" "$dest"; then
    echo "$src -> $dest"
    moved=$((moved+1))
  else
    echo "Failed move: $src" >&2
    failed=$((failed+1))
  fi
done < "$RUN_DIR/surplus_batch.tsv"

echo "Moved files:            $moved"
echo "Failed moves:           $failed"
echo "Staged duplicates in:   $TRASH"
echo "Logs and lists in:      $RUN_DIR"
