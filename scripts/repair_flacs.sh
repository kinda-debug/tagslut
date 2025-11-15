#!/usr/bin/env bash
# repair_flacs.sh
# Usage: ./repair_flacs.sh "/path/to/_quarantine_bad_flacs" "/path/to/_repaired_flacs"

set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 SRC_ROOT DEST_ROOT [SEARCH_ROOT]"
  echo "If SEARCH_ROOT is provided, any file with the same basename found under SEARCH_ROOT"
  echo "that passes 'flac --test' will be copied to DEST and repair will be skipped."
  exit 2
fi

SRC_ROOT="${1%/}"
DEST_ROOT="${2%/}"
SEARCH_ROOT=""
if [ "${3-}" != "" ]; then
  SEARCH_ROOT="${3%/}"
fi
LOGFILE="$(pwd)/repair_flacs_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$DEST_ROOT"

echo "Repairing FLACs from $SRC_ROOT → $DEST_ROOT"

# Adjust PATH if ffmpeg is installed in a non-standard location
# export PATH="/usr/local/bin:$PATH"

find "$SRC_ROOT" -type f -iname '*.flac' -print0 | while IFS= read -r -d '' file; do
  # Compute path relative to the source root (safe parameter expansion)
  rel="${file#$SRC_ROOT/}"
  outdir="$DEST_ROOT/$(dirname "$rel")"
  mkdir -p "$outdir"
  out="$outdir/$(basename "$file")"

  # Initialize per-file flag for skipping repair when a healthy copy exists
  skip_repair=0

  # If SEARCH_ROOT is provided, look for a healthy copy with the same basename.
  # If found, copy it into the destination and skip remuxing.
  if [ -n "$SEARCH_ROOT" ]; then
    name="$(basename "$file")"
    # Find files with the same basename under SEARCH_ROOT (null-delimited)
    while IFS= read -r -d '' cand; do
      # skip the source file if it happens to be inside SEARCH_ROOT
      if [ "$cand" = "$file" ]; then
        continue
      fi
      # Quick test: run flac --test on the candidate; append stderr to logfile
      if flac --test "$cand" >/dev/null 2>>"$LOGFILE"; then
        echo "Found healthy copy: $cand — copying to $out" | tee -a "$LOGFILE"
        # Preserve timestamps/permissions where possible
        cp -p "$cand" "$out"
        skip_repair=1
        break
      fi
    done < <(find "$SEARCH_ROOT" -type f -iname "$name" -print0 2>/dev/null)
  fi

  if [ "$skip_repair" -eq 1 ]; then
    echo "Skipped repair; used healthy copy for: $file" | tee -a "$LOGFILE"
    echo "Rewrapped (copied healthy): $file → $out"
    continue
  fi

  # Quick existence/readability check (helps diagnose odd path truncation)
  if [ ! -e "$file" ]; then
    echo "Input missing: $file" | tee -a "$LOGFILE"
    echo "Failed to repair: $file"
    continue
  fi

  # Use a temporary output file that preserves the final .flac extension
  # so ffmpeg can auto-detect the muxer (some temp suffixes confuse it).
  out_tmp="${out%.flac}.tmp.$$.flac"

  # Run ffmpeg and append stderr to a log for debugging. Force the flac
  # muxer with -f flac to avoid errors when the filename extension is
  # ambiguous to ffmpeg.
  if ffmpeg -v error -i "$file" -c:a flac -f flac -y "$out_tmp" 2>>"$LOGFILE"; then
    mv -- "$out_tmp" "$out"
    echo "Rewrapped: $file → $out" | tee -a "$LOGFILE"
  else
    echo "ffmpeg failed for: $file" | tee -a "$LOGFILE"
    rm -f -- "$out_tmp"
    echo "Failed to repair: $file"
  fi

done

echo "Repair pass complete; check $DEST_ROOT."