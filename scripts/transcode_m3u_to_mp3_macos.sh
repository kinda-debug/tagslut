#!/usr/bin/env bash
set -euo pipefail

# transcode_m3u_to_mp3_macos.sh
#
# Usage:
#   ./transcode_m3u_to_mp3_macos.sh \
#     /Volumes/MUSIC/DJ_LIBRARY/lexicon_newlyadded_dj_pruned_rest_20260312_100447.m3u \
#     /Volumes/MUSIC/DJ_POOL_MANUAL_MP3 \
#     320k \
#     8

PLAYLIST="${1:-}"
OUTDIR="${2:-$HOME/Music/DJ_POOL_MP3}"
BITRATE="${3:-320k}"
JOBS="${4:-}"

if [[ -z "$PLAYLIST" ]]; then
  echo "Usage: $0 <playlist.m3u> [output_dir] [bitrate] [jobs]"
  exit 1
fi

if [[ ! -f "$PLAYLIST" ]]; then
  echo "Playlist not found: $PLAYLIST"
  exit 1
fi

if [[ -z "$JOBS" ]]; then
  if command -v sysctl >/dev/null 2>&1; then
    JOBS="$(sysctl -n hw.logicalcpu 2>/dev/null || true)"
  fi
  JOBS="${JOBS:-4}"
fi

mkdir -p "$OUTDIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
WORKDIR="$(mktemp -d "/tmp/transcode_m3u_to_mp3_${STAMP}_XXXXXX")"
LOGFILE="$OUTDIR/transcode_${STAMP}.log"
QUEUEFILE="$WORKDIR/queue.nul"
WORKER="$WORKDIR/transcode_worker.sh"

cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

playlist_dir="$(cd "$(dirname "$PLAYLIST")" && pwd)"
playlist_abs="$(cd "$(dirname "$PLAYLIST")" && pwd)/$(basename "$PLAYLIST")"

echo "Playlist : $playlist_abs" | tee -a "$LOGFILE"
echo "Out dir  : $OUTDIR" | tee -a "$LOGFILE"
echo "Bitrate  : $BITRATE" | tee -a "$LOGFILE"
echo "Jobs     : $JOBS" | tee -a "$LOGFILE"
echo "Log file : $LOGFILE" | tee -a "$LOGFILE"
echo | tee -a "$LOGFILE"

resolve_path() {
  local raw="$1"
  raw="${raw#$'\xef\xbb\xbf'}"
  raw="${raw%$'\r'}"

  if [[ "$raw" = /* ]]; then
    printf '%s\n' "$raw"
  else
    printf '%s\n' "$playlist_dir/$raw"
  fi
}

build_queue() {
  : > "$QUEUEFILE"

  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^# ]] && continue

    src="$(resolve_path "$line")"

    if [[ ! -f "$src" ]]; then
      printf 'MISSING\t%s\n' "$src" | tee -a "$LOGFILE"
      continue
    fi

    base="$(basename "$src")"
    name="${base%.*}"
    dest="$OUTDIR/$name.mp3"

    printf '%s\0%s\0' "$src" "$dest" >> "$QUEUEFILE"
  done < "$PLAYLIST"
}

cat > "$WORKER" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

src="$1"
dest="$2"
bitrate="$3"
logfile="$4"

tmp_dest="${dest}.part.mp3"

if [[ -f "$dest" ]]; then
  printf 'SKIP\t%s\t%s\n' "$src" "$dest" >> "$logfile"
  exit 0
fi

mkdir -p "$(dirname "$dest")"

if ffmpeg -hide_banner -loglevel error -nostdin -y \
    -i "$src" \
    -map 0:a:0 \
    -map 0:v? \
    -map_metadata 0 \
    -c:a libmp3lame \
    -b:a "$bitrate" \
    -id3v2_version 3 \
    -c:v copy \
    -f mp3 \
    "$tmp_dest"
then
  mv -f "$tmp_dest" "$dest"
  printf 'OK\t%s\t%s\n' "$src" "$dest" >> "$logfile"
  exit 0
fi

rm -f "$tmp_dest"

if ffmpeg -hide_banner -loglevel error -nostdin -y \
    -i "$src" \
    -map 0:a:0 \
    -map_metadata 0 \
    -c:a libmp3lame \
    -b:a "$bitrate" \
    -id3v2_version 3 \
    -f mp3 \
    "$tmp_dest"
then
  mv -f "$tmp_dest" "$dest"
  printf 'OK_NOART\t%s\t%s\n' "$src" "$dest" >> "$logfile"
  exit 0
fi

rm -f "$tmp_dest"
printf 'ERROR\t%s\t%s\n' "$src" "$dest" >> "$logfile"
exit 1
EOF

chmod +x "$WORKER"

build_queue

queued_count="$(python3 - <<'PY' "$QUEUEFILE"
from pathlib import Path
data = Path(__import__("sys").argv[1]).read_bytes()
print(len([x for x in data.split(b"\0") if x]) // 2)
PY
)"
echo "Queued files: $queued_count" | tee -a "$LOGFILE"
echo | tee -a "$LOGFILE"

if [[ "$queued_count" -eq 0 ]]; then
  echo "Nothing to transcode." | tee -a "$LOGFILE"
  exit 0
fi

python3 - <<'PY' "$QUEUEFILE" "$WORKER" "$BITRATE" "$LOGFILE" "$JOBS"
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import subprocess
import sys

queuefile, worker, bitrate, logfile, jobs = sys.argv[1:6]
jobs = int(jobs)

data = Path(queuefile).read_bytes().split(b"\0")
items = [x.decode("utf-8") for x in data if x]
pairs = list(zip(items[0::2], items[1::2]))

rc = 0
with ThreadPoolExecutor(max_workers=jobs) as ex:
    futs = [ex.submit(subprocess.run, [worker, src, dest, bitrate, logfile], check=False) for src, dest in pairs]
    for fut in as_completed(futs):
        result = fut.result()
        if result.returncode != 0:
            rc = 1

sys.exit(rc)
PY

ok_count="$(grep -c '^OK	' "$LOGFILE" 2>/dev/null || true)"
ok_noart_count="$(grep -c '^OK_NOART	' "$LOGFILE" 2>/dev/null || true)"
skip_count="$(grep -c '^SKIP	' "$LOGFILE" 2>/dev/null || true)"
missing_count="$(grep -c '^MISSING	' "$LOGFILE" 2>/dev/null || true)"
error_count="$(grep -c '^ERROR	' "$LOGFILE" 2>/dev/null || true)"

echo | tee -a "$LOGFILE"
echo "Summary:" | tee -a "$LOGFILE"
echo "  Queued       : $queued_count" | tee -a "$LOGFILE"
echo "  OK           : $ok_count" | tee -a "$LOGFILE"
echo "  OK (no art)  : $ok_noart_count" | tee -a "$LOGFILE"
echo "  Skipped      : $skip_count" | tee -a "$LOGFILE"
echo "  Missing      : $missing_count" | tee -a "$LOGFILE"
echo "  Errors       : $error_count" | tee -a "$LOGFILE"
echo | tee -a "$LOGFILE"
echo "Detailed log: $LOGFILE" | tee -a "$LOGFILE"

if [[ "$error_count" -gt 0 || "$missing_count" -gt 0 ]]; then
  exit 2
fi
