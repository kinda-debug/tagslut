#!/usr/bin/env bash
set -euo pipefail

# Strip an ID3v2 tag (if present) from a list of files, then attempt flac verification
# and remux to a repaired file. Does not overwrite originals; creates a backup.
# Usage: ./scripts/strip_id3v2_and_retry.sh /path/to/list.txt

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/list.txt" >&2
  exit 2
fi

LIST_FILE="$1"
[ -f "$LIST_FILE" ] || { echo "List file not found: $LIST_FILE" >&2; exit 2; }

LOGFILE="strip_id3v2_retry_$(date +%Y%m%d_%H%M%S).log"
echo "Strip ID3v2 retry log: $LOGFILE" | tee -a "$LOGFILE"

while IFS= read -r file || [ -n "$file" ]; do
  file="${file%$'\r'}"
  [ -z "$file" ] && continue
  echo "---" | tee -a "$LOGFILE"
  echo "Processing: $file" | tee -a "$LOGFILE"
  if [ ! -f "$file" ]; then
    echo "MISSING: $file" | tee -a "$LOGFILE"
    continue
  fi

  # read first 10 bytes
  head10=$(dd if="$file" bs=1 count=10 2>/dev/null | xxd -p -c 256)
  magic=$(printf "%s" "$head10" | sed -E 's/^(.{6}).*$/\1/')

  # Check for ASCII 'ID3' at start
  if dd if="$file" bs=1 count=3 2>/dev/null | grep -q "^ID3"; then
    echo "ID3v2 tag detected" | tee -a "$LOGFILE"
    # Read size bytes (bytes 6..9) as synchsafe integer
    size_bytes=$(dd if="$file" bs=1 skip=6 count=4 2>/dev/null | xxd -p -c 4)
    # parse synchsafe
    s1=$((16#${size_bytes:0:2}))
    s2=$((16#${size_bytes:2:4}))
    s3=$((16#${size_bytes:4:6}))
    s4=$((16#${size_bytes:6:8}))
    synchsafe=$(((s1 & 0x7f) << 21 | (s2 & 0x7f) << 14 | (s3 & 0x7f) << 7 | (s4 & 0x7f)))
    total_tag_size=$((10 + synchsafe))
    echo "ID3v2 size: $synchsafe, total bytes to skip: $total_tag_size" | tee -a "$LOGFILE"

    # backup original
    bak="${file}.bak.$(date +%Y%m%d_%H%M%S)"
    cp -a "$file" "$bak"
    echo "Backed up to $bak" | tee -a "$LOGFILE"

    stripped="${file%.flac}.id3stripped.$$.flac"
    echo "Writing stripped file -> $stripped" | tee -a "$LOGFILE"
    # Use dd to skip tag bytes
    dd if="$file" bs=1 skip=$total_tag_size of="$stripped" status=none || {
      echo "dd failed" | tee -a "$LOGFILE"
      rm -f "$stripped"
      continue
    }

    echo "Verifying stripped file with flac --test" | tee -a "$LOGFILE"
    if flac --test "$stripped" >>"$LOGFILE" 2>&1; then
      echo "Stripped OK" | tee -a "$LOGFILE"
      out_tmp="${file%.flac}.id3repaired.$$..flac"
      if ffmpeg -v error -f flac -i "$stripped" -map_metadata -1 -c:a flac -f flac -y "$out_tmp" 2>>"$LOGFILE"; then
        final="${file%.flac}.repaired.flac"
        mv -v "$out_tmp" "$final" | tee -a "$LOGFILE"
        echo "OK_REPAIRED: $file -> $final" | tee -a "$LOGFILE"
        rm -f "$stripped"
      else
        echo "FAIL_REMUX_AFTER_STRIP: $file" | tee -a "$LOGFILE"
      fi
    else
      echo "STRIPPED_BAD: $file" | tee -a "$LOGFILE"
      rm -f "$stripped"
    fi
  else
    echo "No ID3v2 tag present" | tee -a "$LOGFILE"
  fi
done < "$LIST_FILE"

echo "Done. See $LOGFILE" | tee -a "$LOGFILE"
