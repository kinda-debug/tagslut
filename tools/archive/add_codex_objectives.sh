#!/usr/bin/env bash
set -e

FILE=".codex/REPO_SURFACE.md"

if [ ! -f "$FILE" ]; then
  echo "ERROR: $FILE not found"
  exit 1
fi

if grep -q "## Objectives" "$FILE"; then
  echo "Objectives section already exists. Skipping."
else
  cat <<'EOF' >> "$FILE"

## Objectives

Primary objective
Maintain a working CLI tool for managing the music library and DJ workflow.

Key goals
- Preserve current CLI behavior.
- Keep the database schema valid and migrations safe.
- Maintain the DJ pipeline (mp3 → dj → XML export).
- Fix bugs with minimal changes.

Avoid
- large refactors
- speculative redesigns
- changing database structure unless required.

EOF
  echo "Objectives section added."
fi

if grep -q "## Task types" "$FILE"; then
  echo "Task types section already exists. Skipping."
else
  cat <<'EOF' >> "$FILE"

## Task types

Bug fix
- reproduce the error
- inspect the relevant module
- apply the smallest patch
- verify with pytest

CLI change
- inspect the command module
- update argument parsing or behavior
- update tests if needed

Database task
- inspect storage/v3
- verify migration safety
- update schema or queries if required

DJ pipeline task
- inspect dj/ and exec/
- modify only the stage involved
- verify using DJ tests

EOF
  echo "Task types section added."
fi

echo "Done."
