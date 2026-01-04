#!/usr/bin/env bash
#
# Find corrupt FLAC files in any directory tree.
# Outputs paths of files that fail 'flac -t'.
#
# Usage:
#   tools/find_corrupt_flacs.sh /Volumes/sad/_DUPE_REVIEW
#   tools/find_corrupt_flacs.sh /Volumes/sad/_DUPE_REVIEW > corrupt_list.txt
#   tools/find_corrupt_flacs.sh /Volumes/sad --move-to /Volumes/sad/_CORRUPT

set -euo pipefail

SEARCH_ROOT="${1:-.}"
MOVE_TO="${2:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [DIRECTORY] [--move-to DEST]

Find corrupt FLAC files using 'flac -t'.

Arguments:
  DIRECTORY    Directory to scan (default: current directory)
  --move-to    Optional destination to move corrupt files

Examples:
  # Find and list
  $(basename "$0") /Volumes/sad/_DUPE_REVIEW

  # Save to file
  $(basename "$0") /Volumes/sad/_DUPE_REVIEW > corrupt_list.txt

  # Find and move to quarantine
  $(basename "$0") /Volumes/sad/_DUPE_REVIEW --move-to /Volumes/sad/_CORRUPT
EOF
  exit 1
}

# Check for flac command
if ! command -v flac &>/dev/null; then
  echo "ERROR: 'flac' command not found"
  echo "Install with: brew install flac"
  exit 1
fi

# Handle --move-to flag
if [[ "${2:-}" == "--move-to" ]]; then
  MOVE_TO="$3"
  mkdir -p "$MOVE_TO"
fi

if [[ ! -d "$SEARCH_ROOT" ]]; then
  echo "ERROR: Directory not found: $SEARCH_ROOT"
  usage
fi

echo "Scanning: $SEARCH_ROOT" >&2
echo "Testing FLAC integrity..." >&2
echo >&2

corrupt_count=0

find "$SEARCH_ROOT" -type f -iname '*.flac' -print0 | while IFS= read -r -d '' file; do
  if ! flac -t -s "$file" >/dev/null 2>&1; then
    echo "CORRUPT: $file"
    ((corrupt_count++)) || true
    
    if [[ -n "$MOVE_TO" ]]; then
      # Preserve relative path structure
      rel_path="${file#$SEARCH_ROOT/}"
      dest_dir="$MOVE_TO/$(dirname "$rel_path")"
      mkdir -p "$dest_dir"
      mv "$file" "$dest_dir/"
      echo "  → moved to $dest_dir/" >&2
    fi
  fi
done

echo >&2
echo "Scan complete. Found $corrupt_count corrupt files." >&2
