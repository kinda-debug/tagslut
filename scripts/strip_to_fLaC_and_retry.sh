#!/usr/bin/env bash
set -euo pipefail

# Strip any leading bytes before the 'fLaC' marker and retry verification/remux.
# Usage: ./scripts/strip_to_fLaC_and_retry.sh /path/to/list.txt
# The list file should be newline-separated absolute paths.

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/list.txt" >&2
  exit 2
fi

LIST_FILE="$1"
[ -f "$LIST_FILE" ] || { echo "List file not found: $LIST_FILE" >&2; exit 2; }

LOGFILE="strip_fLaC_retry_$(date +%Y%m%d_%H%M%S).log"
echo "Strip->fLaC retry log: $LOGFILE" | tee -a "$LOGFILE"

while IFS= read -r file || [ -n "$file" ]; do
  file="${file%$'\r'}"
  [ -z "$file" ] && continue
  echo "---" | tee -a "$LOGFILE"
  echo "Processing: $file" | tee -a "$LOGFILE"
  if [ ! -f "$file" ]; then
    echo "MISSING: $file" | tee -a "$LOGFILE"
    continue
  fi

  # Find offset of the 'fLaC' marker using a small Python stream search (memory-friendly).
  offset_tmp=$(mktemp)
  python3 - "$file" > "$offset_tmp" <<'PY'
import sys
from pathlib import Path

fpath = sys.argv[1]
needle = b'fLaC'
bufsize = 1024*64
pos = 0
found = -1
with open(fpath, 'rb') as fh:
    overlap = b''
    while True:
        chunk = fh.read(bufsize)
        if not chunk:
            break
        data = overlap + chunk
        idx = data.find(needle)
        if idx != -1:
            found = pos + idx - len(overlap)
            break
        # keep last len(needle)-1 bytes as overlap
        overlap = data[-(len(needle)-1):]
        pos += len(chunk)
print(found)
PY
  offset=$(cat "$offset_tmp") || offset=-1
  rm -f "$offset_tmp"

  echo "Found fLaC offset: $offset" | tee -a "$LOGFILE"
  if [ "$offset" -lt 0 ]; then
    echo "NO_FLAC_MARKER: $file" | tee -a "$LOGFILE"
    continue
  fi

  stripped="${file%.flac}.stripped.$$.flac"
  echo "Creating stripped file starting at $offset -> $stripped" | tee -a "$LOGFILE"

  # Copy from offset to new file using Python to avoid slow dd with bs=1
  python3 - <<'PY' > /dev/null 2>>"$LOGFILE"
import sys
src = sys.argv[1]
dst = sys.argv[2]
offset = int(sys.argv[3])
buf = 1024*1024
with open(src, 'rb') as fr, open(dst, 'wb') as fw:
    fr.seek(offset)
    while True:
        data = fr.read(buf)
        if not data:
            break
        fw.write(data)
PY
  # call python with args via environment to avoid heredoc-arg parsing issues
  python3 -c "import sys; from pathlib import Path; src=\"$file\"; dst=\"$stripped\"; offset=int($offset); buf=1024*1024
with open(src,'rb') as fr, open(dst,'wb') as fw:
    fr.seek(offset)
    while True:
        data=fr.read(buf)
        if not data: break
        fw.write(data)"

  echo "Verifying stripped file with flac --test" | tee -a "$LOGFILE"
  if flac --test "$stripped" >>"$LOGFILE" 2>&1; then
    echo "Stripped file OK: $stripped" | tee -a "$LOGFILE"
    # Remux to a fresh flac to normalize container and strip metadata
    out_tmp="${file%.flac}.fromstripped.retry.$$.flac"
    echo "Remuxing stripped file -> $out_tmp" | tee -a "$LOGFILE"
    if ffmpeg -v error -f flac -i "$stripped" -map_metadata -1 -c:a flac -f flac -y "$out_tmp" 2>>"$LOGFILE"; then
      final="${file%.flac}.repaired.flac"
      mv -v "$out_tmp" "$final" | tee -a "$LOGFILE"
      echo "OK_REPAIRED: $file -> $final" | tee -a "$LOGFILE"
      rm -f "$stripped"
    else
      echo "FAIL_REMUX_AFTER_STRIP: $file" | tee -a "$LOGFILE"
      # keep stripped for inspection
    fi
  else
    echo "STRIPPED_BAD: $file" | tee -a "$LOGFILE"
    rm -f "$stripped"
  fi
done < "$LIST_FILE"

echo "Done. See $LOGFILE" | tee -a "$LOGFILE"
