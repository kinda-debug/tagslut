#!/usr/bin/env bash
set -euo pipefail

QUAR="/Volumes/dotad/MUSIC/_quarantine_from_gemini"
ROOT="/Volumes/dotad/MUSIC"
OUT="quarantine_hash_verification.csv"

echo "quarantine_path,match_count,match_paths,quarantine_md5" > "$OUT"

# Build hash index for main library (excluding quarantine)
echo "[i] Hashing main library..."
declare -A LIB_INDEX
while IFS= read -r f; do
    h=$(ffmpeg -v error -i "$f" -map 0:a -f md5 - 2>/dev/null | awk '{print $NF}')
    [[ -n "$h" ]] && LIB_INDEX["$h"]+="$f|"
done < <(find "$ROOT" -type f -name "*.flac" ! -path "$QUAR/*")

# Check quarantine files against the index
echo "[i] Verifying quarantined files..."
find "$QUAR" -type f -name "*.flac" | while IFS= read -r q; do
    q_md5=$(ffmpeg -v error -i "$q" -map 0:a -f md5 - 2>/dev/null | awk '{print $NF}')
    matches="${LIB_INDEX[$q_md5]:-}"
    if [[ -n "$matches" ]]; then
        count=$(echo "$matches" | tr '|' '\n' | grep -v '^$' | wc -l | tr -d ' ')
        echo "\"$q\",\"$count\",\"$matches\",\"$q_md5\"" >> "$OUT"
        echo "[ DUPLICATE $count ] $q"
    else
        echo "\"$q\",0,,\"$q_md5\"" >> "$OUT"
        echo "[ UNIQUE ] $q"
    fi
done

echo "[✓] Wrote $OUT"
