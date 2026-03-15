#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOMATION_DIR="${CODEX_HOME:-$HOME/.codex}/automations/post-work-chain"
AUTOMATION_TOML="$AUTOMATION_DIR/automation.toml"

if [[ ! -f "$AUTOMATION_TOML" ]]; then
  echo "Missing automation config: $AUTOMATION_TOML" >&2
  exit 1
fi

git -C "$REPO_ROOT" push "$@"

PROMPT="$(
python3 - <<'PY' "$AUTOMATION_TOML"
from pathlib import Path
import sys
import tomllib

automation_toml = Path(sys.argv[1])
data = tomllib.loads(automation_toml.read_text())
print(data["prompt"])
PY
)"

exec codex exec \
  --full-auto \
  --add-dir "$AUTOMATION_DIR" \
  -C "$REPO_ROOT" \
  "$PROMPT"
