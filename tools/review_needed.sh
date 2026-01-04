#!/usr/bin/env bash
#
# Review helper for files flagged REVIEW by recommend_keepers.py
# Opens files side-by-side and shows decision context.
#
# Usage:
#   tools/review_needed.sh recommendations.csv group_0042
#   tools/review_needed.sh recommendations.csv /full/path/to/file.flac
#
# Requires:
#   - VS Code 'code' command
#   - mpv (optional, for quick playback)
#   - fzf (optional, for interactive selection)

set -euo pipefail

RECS_CSV="${1:-}"
FILTER="${2:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") RECOMMENDATIONS_CSV [FILTER]

Review files flagged REVIEW by decision engine.

Arguments:
  RECOMMENDATIONS_CSV    CSV output from recommend_keepers.py
  FILTER                 Optional filter (group ID, path substring, or 'REVIEW')

Examples:
  # Review all REVIEW decisions
  $(basename "$0") /tmp/recovery_recs.csv REVIEW

  # Review specific group from _DUPE_REVIEW
  $(basename "$0") /tmp/recovery_recs.csv group_0042

  # Interactive selection
  $(basename "$0") /tmp/recovery_recs.csv | fzf

  # Review specific file
  $(basename "$0") /tmp/recovery_recs.csv "/Volumes/RECOVERY_TARGET/Root/..."
EOF
  exit 1
}

[[ -z "$RECS_CSV" ]] && usage
[[ ! -f "$RECS_CSV" ]] && echo "ERROR: File not found: $RECS_CSV" && exit 1

# Filter CSV
if [[ -z "$FILTER" ]]; then
  # No filter: show all
  MATCHES=$(tail -n +2 "$RECS_CSV")
elif [[ "$FILTER" == "REVIEW" ]]; then
  # Show only REVIEW decisions
  MATCHES=$(tail -n +2 "$RECS_CSV" | grep ",REVIEW,")
else
  # Substring match on path
  MATCHES=$(tail -n +2 "$RECS_CSV" | grep -i "$FILTER")
fi

# Count matches
NUM_MATCHES=$(echo "$MATCHES" | wc -l | tr -d ' ')

if [[ -z "$MATCHES" || "$NUM_MATCHES" -eq 0 ]]; then
  echo "No matches found for: $FILTER"
  exit 1
fi

echo "Found $NUM_MATCHES matching files:"
echo "$MATCHES" | cut -d',' -f1,2,3,4 | column -t -s','
echo

# Extract paths
PATHS=$(echo "$MATCHES" | cut -d',' -f1)

# Check if these are _DUPE_REVIEW paths
if echo "$PATHS" | head -1 | grep -q "_DUPE_REVIEW"; then
  # Group review mode
  GROUP_DIR=$(echo "$PATHS" | head -1 | grep -o '_DUPE_REVIEW/group_[0-9]*' | head -1)
  
  if [[ -n "$GROUP_DIR" ]]; then
    echo "Opening group: $GROUP_DIR"
    REVIEW_ROOT="${DUPE_REVIEW_ROOT:-/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/_DUPE_REVIEW}"
    FULL_DIR="$REVIEW_ROOT/$(basename "$GROUP_DIR")"
    
    if [[ -d "$FULL_DIR" ]]; then
      # Use open_dupe_pair.sh if available
      if [[ -x "$(dirname "$0")/open_dupe_pair.sh" ]]; then
        exec "$(dirname "$0")/open_dupe_pair.sh" "$FULL_DIR"
      fi
      
      # Fallback: direct VS Code open
      mapfile -t FILES < <(find "$FULL_DIR" -type f -iname '*.flac' | sort)
      echo "Opening ${#FILES[@]} files in VS Code..."
      code -n "${FILES[@]}"
      exit 0
    fi
  fi
fi

# Original path mode: open all matching files
mapfile -t FILE_ARRAY < <(echo "$PATHS")

if [[ ${#FILE_ARRAY[@]} -le 10 ]]; then
  # Few files: open directly
  echo "Opening ${#FILE_ARRAY[@]} files in VS Code..."
  code -n "${FILE_ARRAY[@]}"
else
  # Many files: offer interactive selection
  if command -v fzf &>/dev/null; then
    echo "Too many files (${#FILE_ARRAY[@]}). Use fzf to select:"
    SELECTED=$(echo "$PATHS" | fzf --multi --header="Select files to open (Tab to multi-select)")
    
    if [[ -n "$SELECTED" ]]; then
      mapfile -t SELECTED_ARRAY < <(echo "$SELECTED")
      code -n "${SELECTED_ARRAY[@]}"
    fi
  else
    echo "ERROR: Too many files (${#FILE_ARRAY[@]}) to open at once"
    echo "Install fzf for interactive selection: brew install fzf"
    exit 1
  fi
fi
