#!/bin/bash
# sync_music.sh
# Sync /Volumes/sad/MUSIC -> /Volumes/red/MUSIC with checks, mkdir, and timer

set -euo pipefail

SRC="/Volumes/sad/MUSIC/"
DST="/Volumes/red/MUSIC/"
DST_DIR="${DST%/}"            # strip trailing slash for tests
DST_VOL="/Volumes/red"

log() { printf "▶ %s\n" "$*"; }

# 0) Don’t run via 'source'
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo "This script was sourced. Run it like:  bash \"$0\""
  return 1 2>/dev/null || exit 1
fi

START=$(date +%s)

# 1) Basic checks
if [[ ! -d "$SRC" ]]; then
  echo "Source folder not found: $SRC"
  exit 1
fi

if [[ ! -d "$DST_VOL" ]]; then
  echo "Destination volume not mounted: $DST_VOL"
  exit 1
fi

# 2) Ensure destination folder exists
if [[ ! -d "$DST_DIR" ]]; then
  log "Creating destination folder: $DST_DIR"
  mkdir -p "$DST_DIR"
fi

# 3) Quick write test on destination volume
TESTFILE="$DST_DIR/.rsync_write_test_$$"
if ! ( : > "$TESTFILE" 2>/dev/null ); then
  echo "Cannot write to destination: $DST_DIR"
  exit 1
fi
rm -f "$TESTFILE"

# 4) Optional: free space sanity check (best-effort)
# Get rough sizes in KiB; if parsing fails we skip the check.
get_kib() { du -sk "$1" 2>/dev/null | awk '{print $1}'; }
SRC_KIB=$(get_kib "$SRC" || echo "")
DST_KIB=$(get_kib "$DST_DIR" || echo "")
FREE_KIB=$(df -k "$DST_VOL" 2>/dev/null | awk 'NR==2 {print $4}')

if [[ -n "$SRC_KIB" && -n "$DST_KIB" && -n "$FREE_KIB" ]]; then
  # Worst-case needed equals the delta (very rough). Add 2% buffer.
  DELTA_KIB=$(( SRC_KIB > DST_KIB ? SRC_KIB - DST_KIB : 0 ))
  BUFFER_KIB=$(( (DELTA_KIB * 2) / 100 ))
  NEED_KIB=$(( DELTA_KIB + BUFFER_KIB ))
  if (( FREE_KIB < NEED_KIB )); then
    log "Warning: free space may be low on $DST_VOL (need ~${NEED_KIB}K, have ${FREE_KIB}K). Continuing anyway…"
  fi
fi

# 5) Do the sync (no dry run). --delete keeps strict mirror.
log "Starting rsync…"
rsync -avh --info=progress2 --delete "$SRC" "$DST"

END=$(date +%s)
ELAPSED=$(( END - START ))
log "Sync finished in $(date -u -r "$ELAPSED" +%H:%M:%S)"
