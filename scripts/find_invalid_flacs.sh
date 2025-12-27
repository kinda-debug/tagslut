#!/usr/bin/env bash
# find_invalid_flacs.sh
# Usage: ./find_invalid_flacs.sh "/path/to/MUSIC" "/path/to/_quarantine_bad_flacs"

set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 LIB_ROOT QUARANTINE_ROOT"
  exit 2
fi

LIB_ROOT="${1%/}"
QUARANTINE_ROOT="${2%/}"
LOGFILE="$(pwd)/invalid_flacs_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$QUARANTINE_ROOT"

echo "Logging failed files to $LOGFILE"

# Adjust PATH if your flac binary is installed in a non-standard location
# export PATH="/usr/local/bin:$PATH"

# Use find -print0 to safely handle spaces/newlines in filenames
find "$LIB_ROOT" -type f -iname '*.flac' -print0 | while IFS= read -r -d '' file; do
  # run official validator; append output to log for debugging
  if ! flac --test "$file" &>>"$LOGFILE"; then
    echo "INVALID: $file" | tee -a "$LOGFILE"

    # replicate directory structure inside quarantine
    # remove LIB_ROOT prefix safely
    relpath="${file#$LIB_ROOT/}"
    target_dir="$QUARANTINE_ROOT/$(dirname "$relpath")"
    mkdir -p "$target_dir"

    # move the invalid file into quarantine
    mv -- "$file" "$target_dir/"
  fi
done

echo "Done. See $LOGFILE and quarantined files under $QUARANTINE_ROOT."