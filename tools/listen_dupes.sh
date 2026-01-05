#!/usr/bin/env bash
#
# Interactive FLAC listening tool using fzf + mpv.
# Fast terminal-based audio preview for dupe comparison.
#
# Usage:
#   ./tools/listen_dupes.sh                    # Browse all files in review root
#   ./tools/listen_dupes.sh group_0001         # Browse specific group
#   ./tools/listen_dupes.sh filelist.txt       # Browse from file list
#
# Requires:
#   - fzf (brew install fzf)
#   - mpv (brew install mpv)
#
# Controls (in fzf):
#   ↑/↓     Navigate files
#   Enter   Select file (prints path)
#   Esc     Quit
#   Preview plays automatically on hover

set -euo pipefail

REVIEW_ROOT="${DUPE_REVIEW_ROOT:-/Volumes/COMMUNE/10_STAGING/_DUPE_REVIEW}"
PREVIEW_LENGTH="${PREVIEW_LENGTH:-15}"
PREVIEW_VOLUME="${PREVIEW_VOLUME:-50}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [GROUP_ID|FILE_LIST]

Interactive FLAC listening tool for dupe comparison.

Arguments:
  GROUP_ID    Browse specific group (e.g., group_0001)
  FILE_LIST   Browse from text file (one path per line)
  (none)      Browse all files in review root

Environment:
  DUPE_REVIEW_ROOT    Root directory for review folders (default: $REVIEW_ROOT)
  PREVIEW_LENGTH      Preview duration in seconds (default: $PREVIEW_LENGTH)
  PREVIEW_VOLUME      Playback volume 0-100 (default: $PREVIEW_VOLUME)

Examples:
  $(basename "$0")                    # Browse all
  $(basename "$0") group_0001         # Browse one group
  $(basename "$0") candidates.txt     # Browse from list
EOF
  exit 1
}

# Check dependencies
for cmd in fzf mpv; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "ERROR: Required command not found: $cmd"
    echo "Install with: brew install $cmd"
    exit 1
  fi
done

# Determine input source
if [[ $# -eq 0 ]]; then
  # Browse all files in review root
  if [[ ! -d "$REVIEW_ROOT" ]]; then
    echo "ERROR: Review root not found: $REVIEW_ROOT"
    exit 1
  fi
  INPUT_CMD="find '$REVIEW_ROOT' -type f -iname '*.flac' | sort"
elif [[ -f "$1" ]]; then
  # Browse from file list
  INPUT_CMD="cat '$1'"
elif [[ -d "$REVIEW_ROOT/$1" ]]; then
  # Browse specific group by ID
  INPUT_CMD="find '$REVIEW_ROOT/$1' -type f -iname '*.flac' | sort"
elif [[ -d "$1" ]]; then
  # Browse specific directory path
  INPUT_CMD="find '$1' -type f -iname '*.flac' | sort"
else
  echo "ERROR: Invalid argument: $1"
  usage
fi

# Run fzf with mpv preview
eval "$INPUT_CMD" | fzf \
  --preview="mpv --no-video --force-window=no --volume=$PREVIEW_VOLUME --length=$PREVIEW_LENGTH {} 2>/dev/null" \
  --preview-window=down:4 \
  --height=100% \
  --header="↑/↓ navigate | Enter select | Esc quit | Auto-preview on hover" \
  --border
