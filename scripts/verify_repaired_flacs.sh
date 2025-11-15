#!/usr/bin/env bash
# verify_repaired_flacs.sh
# Usage: ./scripts/verify_repaired_flacs.sh "/path/to/_repaired_flacs"

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 REPAIRED_ROOT"
  exit 2
fi

REPAIRED_ROOT="${1%/}"
OUTFILE="$(pwd)/repaired_flac_test_results_$(date +%Y%m%d_%H%M%S).txt"

if ! command -v flac >/dev/null 2>&1; then
  echo "flac command not found in PATH. Install libflac or adjust PATH." | tee "$OUTFILE"
  exit 2
fi

echo "Verifying FLAC files under: $REPAIRED_ROOT" | tee "$OUTFILE"

count_total=0
count_bad=0

# Use process-substitution so the while loop runs in the current shell (counts persist)
while IFS= read -r -d '' f; do
  echo "Testing: $f" | tee -a "$OUTFILE"
  if flac --test "$f" 2>>"$OUTFILE"; then
    echo "OK: $f" | tee -a "$OUTFILE"
  else
    echo "BAD: $f" | tee -a "$OUTFILE"
    count_bad=$((count_bad+1))
  fi
  count_total=$((count_total+1))
done < <(find "$REPAIRED_ROOT" -type f -iname '*.flac' -print0)

echo "" | tee -a "$OUTFILE"
echo "Summary: total=$count_total  bad=$count_bad" | tee -a "$OUTFILE"

if [ "$count_bad" -eq 0 ]; then
  echo "All repaired files passed flac --test." | tee -a "$OUTFILE"
  exit 0
else
  echo "Some repaired files failed. See $OUTFILE for details." | tee -a "$OUTFILE"
  exit 1
fi
