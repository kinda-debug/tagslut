#!/usr/bin/env bash
set -euo pipefail

# Retry repair for a newline-separated list of FLAC file paths.
# For each file this will:
# - show the first bytes (header) into the log
# - attempt a remux that removes metadata (strips ID3v2) using ffmpeg
# - on success, move the result to '<original>.repaired.flac'
# Usage: ./scripts/retry_repair_list.sh /path/to/list.txt

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/list.txt" >&2
  exit 2
fi

LIST_FILE="$1"

if [ ! -f "$LIST_FILE" ]; then
  echo "List file not found: $LIST_FILE" >&2
  exit 2
fi

LOGFILE="retry_repair_$(date +%Y%m%d_%H%M%S).log"
echo "Retry repair log: $LOGFILE" | tee -a "$LOGFILE"

while IFS= read -r file || [ -n "$file" ]; do
  file="${file%$'\r'}" # strip CR if present
  [ -z "$file" ] && continue
  echo "---" | tee -a "$LOGFILE"
  echo "Processing: $file" | tee -a "$LOGFILE"
  if [ ! -f "$file" ]; then
    echo "MISSING: $file" | tee -a "$LOGFILE"
    continue
  fi

  echo "Header (first 32 bytes):" >> "$LOGFILE"
  xxd -l 32 "$file" >> "$LOGFILE" 2>&1 || true

  out_tmp="${file%.flac}.retry.$$.flac"

  echo "Attempting ffmpeg remux (strip metadata) -> $out_tmp" | tee -a "$LOGFILE"
  if ffmpeg -v error -i "$file" -map_metadata -1 -c:a flac -f flac -y "$out_tmp" 2>>"$LOGFILE"; then
    mv -v "$out_tmp" "${file%.flac}.repaired.flac" | tee -a "$LOGFILE"
    echo "OK_REPAIRED: $file" | tee -a "$LOGFILE"
  else
    echo "FAIL_REPAIR: $file" | tee -a "$LOGFILE"
    [ -f "$out_tmp" ] && rm -f "$out_tmp"
  fi
done < "$LIST_FILE"

echo "Done. See $LOGFILE" | tee -a "$LOGFILE"
