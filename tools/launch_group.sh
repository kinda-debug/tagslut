#!/usr/bin/env zsh
# Usage: tools/launch_group.sh [GROUP]
# Launches Codex exec instances for a named group via Terminal tabs.

set -e

REPO="/Users/georgeskhawam/Projects/tagslut"
PROMPTS="$REPO/.github/prompts"
CODEX="/opt/homebrew/bin/codex"

declare -A GROUPS

# Already done — filesystem ops completed this session
GROUPS[GROUP0]="consolidate-playlists:0 cleanup-djpool-home:0 mp3-consolidate:0"

# Done
GROUPS[GROUP1]="auth-tidal-logout:0 beatport-circuit-breaker:0 dj-pool-named-m3u:0 dj-xml-patch-repair:0 qobuz-routing-tools-get:0"

# Done
GROUPS[GROUP2]="fix-per-stage-resume:0 register-mp3-only:0 intake-pipeline-hardening:0"

# Docs + audit — no file overlaps, all safe to run simultaneously
GROUPS[GROUP3A]="repo-audit-and-plan:0 repo-cleanup:0 repo-cleanup-supplement:120 docs-housekeeping-2026-04:0 docs-housekeeping-2026-04b:120 phase1-pr14-agent-docs-update:0"

# Filesystem-only ops — no source code touched
GROUPS[GROUP3B]="absorb-mp3-to-sort:0 absorb-rbx-usb-bpdl-flacs:0"

# Phase 1 PR chain — STRICT sequential, one at a time
GROUPS[GROUP4A]="phase1-pr9-migration-0006-merge:0"
GROUPS[GROUP4B]="phase1-pr10-identity-service:0"
GROUPS[GROUP4C]="phase1-pr12-identity-merge:0"
GROUPS[GROUP4D]="phase1-pr15-phase2-seam:0"

# Features — after Phase 1 merged
GROUPS[GROUP5]="feat-tidal-native-fields:0 feat-intake-spotiflac:120 feat-spotify-intake-path:240"

# Beets sidecar — self-contained branch, anytime
GROUPS[GROUP6]="beets-sidecar-research:0 beets-sidecar-package:120 feat-beets-sidecar:300"

# Filesystem consolidation + cleanup — independent, run together
GROUPS[GROUP8]="consolidate-mp3-leftovers:0 purge-stale-work:0"
GROUPS[GROUP9]="qobuz-full-intake-pipeline:0"
GROUPS[GROUP10]="triage-work-dirs:0"

# DJ hardening — after GROUP5
GROUPS[GROUP7]="dj-missing-tests-week1:0 dj-pool-wizard-transcode:120 lexicon-reconcile:240"

GROUP="${1:-GROUP3A}"
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
  if [[ -f "$PROMPTS/${name}.md" ]]; then
    prompt_file="$PROMPTS/${name}.md"
  else
    prompt_file="$PROMPTS/${name}.prompt.md"
  fi

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
