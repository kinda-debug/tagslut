#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_wrapper_common.sh"
ts_wrapper_bootstrap "${BASH_SOURCE[0]}"

SELF_PATH="${TAGSLUT_TOOLS_DIR}/_beatportdl.sh"
BEATPORTDL_BIN="${BEATPORTDL_BIN:-}"

if [[ -z "$BEATPORTDL_BIN" && -n "${BEATPORTDL_CMD:-}" && "${BEATPORTDL_CMD}" != "$SELF_PATH" ]]; then
  BEATPORTDL_BIN="$BEATPORTDL_CMD"
fi

if [[ -z "$BEATPORTDL_BIN" ]]; then
  if [[ -x "${TAGSLUT_TOOLS_DIR}/beatportdl/bpdl/beatportdl" ]]; then
    BEATPORTDL_BIN="${TAGSLUT_TOOLS_DIR}/beatportdl/bpdl/beatportdl"
  elif command -v beatportdl >/dev/null 2>&1; then
    BEATPORTDL_BIN="$(command -v beatportdl)"
  else
    ts_die "beatportdl binary not found; set BEATPORTDL_BIN or BEATPORTDL_CMD"
  fi
fi

if [[ -d "$BEATPORTDL_BIN" || ! -x "$BEATPORTDL_BIN" ]]; then
  ts_die "beatportdl binary not found or not executable at: $BEATPORTDL_BIN"
fi

exec env -C "$(dirname "$BEATPORTDL_BIN")" "$BEATPORTDL_BIN" "$@"
