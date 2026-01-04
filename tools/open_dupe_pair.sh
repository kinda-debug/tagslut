#!/usr/bin/env bash
#
# Open a dupe group's files side-by-side in VS Code for A/B comparison.
#
# Usage:
#   ./tools/open_dupe_pair.sh group_0001
#   ./tools/open_dupe_pair.sh /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/_DUPE_REVIEW/group_0042
#
# Requires:
#   - VS Code 'code' command in PATH
#   - Audio Preview extension (optional but recommended)
#   - VSCode-Spectrogram extension (optional for visual analysis)

set -euo pipefail

REVIEW_ROOT="${DUPE_REVIEW_ROOT:-/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/_DUPE_REVIEW}"

usage() {
  cat <<EOF
Usage: $(basename "$0") GROUP_ID

Open dupe group files side-by-side in VS Code.

Arguments:
  GROUP_ID    Group identifier (e.g., group_0001) or full path

Environment:
  DUPE_REVIEW_ROOT    Root directory for review folders (default: $REVIEW_ROOT)

Examples:
  $(basename "$0") group_0001
  $(basename "$0") /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY/_DUPE_REVIEW/group_0042
EOF
  exit 1
}

[ $# -eq 0 ] && usage

GROUP="$1"

# If GROUP is a full path, use it directly; otherwise construct from root
if [[ -d "$GROUP" ]]; then
  DIR="$GROUP"
else
  DIR="$REVIEW_ROOT/$GROUP"
fi

if [[ ! -d "$DIR" ]]; then
  echo "ERROR: Group directory not found: $DIR"
  exit 1
fi

# Get all FLAC files in the group
mapfile -t FILES < <(find "$DIR" -type f -iname '*.flac' | sort)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "ERROR: No FLAC files found in $DIR"
  exit 1
fi

echo "Opening ${#FILES[@]} files from $(basename "$DIR"):"
printf '  %s\n' "${FILES[@]}"
echo

# Open in VS Code (new window to avoid clutter)
code -n "${FILES[@]}"
