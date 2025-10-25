#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/Volumes/dotad/MUSIC}"
OUTDIR="${2:-./health_scan_out}"
mkdir -p "$OUTDIR"
CSV="$OUTDIR/live_health.csv"
BAD="$OUTDIR/corrupt_now.csv"
LOG="$OUTDIR/health_scan.log"

# Extensions to scan
exts='flac|wav|aiff|aif|alac|m4a|mp3|ogg|opus|wma|wv|ape|dsf|dff|mka'

# CPU parallelism (works on macOS/BSD xargs)
P="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"

echo "path,ok,reason,codec,duration_sec,size_bytes" > "$CSV"
: > "$LOG"

scan_one() {
  f="$1"
  # size
  size=$(stat -f %z "$f" 2>/dev/null || stat -c %s "$f" 2>/dev/null || echo "")
  # metadata
  meta=$(ffprobe -v error -select_streams a:0 \
    -show_entries stream=codec_name -show_entries format=duration \
    -of csv=p=0 "$f" 2>>"$LOG" || true)
  codec=$(echo "$meta" | head -n1 | tr -d '\r' | awk -F',' 'NR==1{print $1}')
  dur=$(echo "$meta"  | tail -n1 | tr -d '\r' | awk -F',' 'NR==1{print $1}')
  # decode test
  ok=1; reason=""
  if [[ "${f,,}" == *.flac ]]; then
    if ! flac -s -t "$f" >>"$LOG" 2>&1; then
      ok=0; reason="flac_test_failed"
    fi
  else
    # decode to null; capture errors only
    if ! ffmpeg -v error -nostdin -i "$f" -f null - -y >>"$LOG" 2>&1; then
      ok=0; reason="ffmpeg_decode_error"
    fi
  fi
  echo "$f,$ok,$reason,${codec:-},${dur:-},${size:-}" >> "$CSV"
}

export -f scan_one
export CSV LOG

echo "[i] Scanning: $ROOT"
find "$ROOT" -type f -iregex ".*\.(${exts})$" -print0 \
  | xargs -0 -n1 -P "$P" bash -lc 'scan_one "$@"' _

# extract bads
awk -F',' 'NR==1 || $2=="0"' "$CSV" > "$BAD"

echo "[+] Wrote $CSV"
echo "[+] Wrote $BAD"
