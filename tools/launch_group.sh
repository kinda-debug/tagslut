#!/usr/bin/env zsh
# Usage: tools/launch_group.sh [GROUP]
# Launches Codex exec instances for a named group via Terminal tabs.

set -e

REPO="/Users/georgeskhawam/Projects/tagslut"
PROMPTS="$REPO/.github/prompts"
CODEX="/opt/homebrew/bin/codex"

declare -A GROUPS
GROUPS[GROUP0]="consolidate-playlists:0 cleanup-djpool-home:0 mp3-consolidate:0"
GROUPS[GROUP1]="auth-tidal-logout:0 beatport-circuit-breaker:0 dj-pool-named-m3u:0 dj-xml-patch-repair:0 qobuz-routing-tools-get:0"
GROUPS[GROUP2]="fix-per-stage-resume:0 register-mp3-only:0 intake-pipeline-hardening:120"

GROUP="${1:-GROUP2}"
ENTRIES=(${=GROUPS[$GROUP]})

if [[ -z "$ENTRIES" ]]; then
  echo "Unknown group: $GROUP"
  echo "Available: ${(k)GROUPS}"
  exit 1
fi

echo "Launching $GROUP (${#ENTRIES} prompts)..."

for entry in $ENTRIES; do
  name="${entry%%:*}"
  delay="${entry##*:}"
  prompt_file="$PROMPTS/${name}.prompt.md"

  if [[ ! -f "$prompt_file" ]]; then
    echo "  SKIP: $name (prompt file not found)"
    continue
  fi

  if [[ "$delay" -gt 0 ]]; then
    echo "  Sleeping ${delay}s before $name..."
    sleep "$delay"
  fi

  echo "  Launching: $name"
  osascript -e "tell application \"Terminal\" to do script \"cd '$REPO' && $CODEX exec --full-auto - < '$prompt_file'\""
done

echo "All $GROUP instances launched."
