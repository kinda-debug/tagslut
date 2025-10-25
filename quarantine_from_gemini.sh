#!/usr/bin/env bash
set -euo pipefail

LIST='/Users/georgeskhawam/dev/duplicates selected by gemini.txt'
ROOT="/Volumes/dotad/MUSIC"
QUAR="${ROOT%/}/_quarantine_from_gemini"

mkdir -p "$QUAR"

echo "[i] Starting quarantine from: $LIST"
echo "[i] Quarantine target: $QUAR"

# Count how many paths we'll process
TOTAL=$(grep '^/Volumes/dotad/MUSIC/' "$LIST" | wc -l | tr -d ' ')
echo "[i] Total duplicate files listed: $TOTAL"

i=0
grep '^/Volumes/dotad/MUSIC/' "$LIST" | while IFS= read -r p; do
  i=$((i+1))
  rel="${p#${ROOT%/}/}"
  dest="$QUAR/$rel"
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$p" ]]; then
    mv -v -- "$p" "$dest"
    echo "[✔] ($i/$TOTAL) Moved: $p"
  else
    echo "[⚠] ($i/$TOTAL) Missing: $p"
  fi
done

echo "[✓] Quarantine complete."
