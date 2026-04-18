#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_wrapper_common.sh"
ts_wrapper_bootstrap "${BASH_SOURCE[0]}"

SELF_PATH="${TAGSLUT_TOOLS_DIR}/_beatportdl.sh"
BEATPORTDL_BIN="${BEATPORTDL_BIN:-}"
BEATPORTDL_HOME_DEFAULT="/Users/georgeskhawam/Projects/beatportdl/bin"
BEATPORTDL_CONFIG="${BEATPORTDL_CONFIG:-}"
BEATPORTDL_CREDENTIALS="${BEATPORTDL_CREDENTIALS:-}"

if [[ -z "$BEATPORTDL_BIN" && -n "${BEATPORTDL_CMD:-}" && "${BEATPORTDL_CMD}" != "$SELF_PATH" ]]; then
  BEATPORTDL_BIN="$BEATPORTDL_CMD"
fi

if [[ -z "$BEATPORTDL_BIN" ]]; then
  BEATPORTDL_BIN="${BEATPORTDL_HOME_DEFAULT}/beatportdl-darwin-arm64"
fi

if [[ -d "$BEATPORTDL_BIN" || ! -x "$BEATPORTDL_BIN" ]]; then
  ts_die "beatportdl binary not found or not executable at: $BEATPORTDL_BIN"
fi

if [[ -z "$BEATPORTDL_CONFIG" ]]; then
  BEATPORTDL_CONFIG="${BEATPORTDL_HOME_DEFAULT}/beatportdl-config.yml"
fi
if [[ -z "$BEATPORTDL_CREDENTIALS" ]]; then
  BEATPORTDL_CREDENTIALS="${BEATPORTDL_HOME_DEFAULT}/beatportdl-credentials.json"
fi

[[ -f "$BEATPORTDL_CONFIG" ]] || ts_die "beatportdl config not found at: $BEATPORTDL_CONFIG"
[[ -f "$BEATPORTDL_CREDENTIALS" ]] || ts_die "beatportdl credentials not found at: $BEATPORTDL_CREDENTIALS"

exec env \
  -C "$(dirname "$BEATPORTDL_BIN")" \
  BEATPORTDL_CONFIG="$BEATPORTDL_CONFIG" \
  BEATPORTDL_CREDENTIALS="$BEATPORTDL_CREDENTIALS" \
  "$BEATPORTDL_BIN" "$@"
