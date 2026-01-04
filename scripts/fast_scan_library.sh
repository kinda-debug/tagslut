#!/usr/bin/env bash
# Fast library scan helper: uses larger batch size and verbose logging.
# Usage:
#   scripts/fast_scan_library.sh /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY artifacts/db/library.db [BATCH]
# Example:
#   scripts/fast_scan_library.sh /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY artifacts/db/library.db 2000

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <LIBRARY_ROOT> <OUT_DB> [BATCH_SIZE]" >&2
  exit 1
fi

LIB_ROOT="$1"
OUT_DB="$2"
BATCH_SIZE="${3:-2000}"

python3 -m dedupe.cli scan-library \
  --root "$LIB_ROOT" \
  --out "$OUT_DB" \
  --resume \
  --verbose \
  --batch-size "$BATCH_SIZE"