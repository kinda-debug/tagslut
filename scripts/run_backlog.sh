#!/usr/bin/env bash
# Usage:
#   bash scripts/run_backlog.sh [--dry-run-only] [--skip-reconcile]

set -euo pipefail

DRY_RUN_ONLY=0
SKIP_RECONCILE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run-only) DRY_RUN_ONLY=1; shift ;;
    --skip-reconcile) SKIP_RECONCILE=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load env roughly like START_HERE.sh (but in this subshell)
if [[ -f "$ROOT_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.venv/bin/activate"
else
  echo "Missing venv at $ROOT_DIR/.venv" >&2
  exit 1
fi

if [[ -f "$ROOT_DIR/env_exports.sh" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT_DIR/env_exports.sh"
fi

: "${TAGSLUT_ARTIFACTS:="$ROOT_DIR/artifacts"}"
LOG_DIR="$TAGSLUT_ARTIFACTS/logs"
mkdir -p "$LOG_DIR"

timestamp() { date +%Y%m%d_%H%M%S; }

START_TS="$(timestamp)"
START_SEC="$(date +%s)"

EXCEL_LOG="$LOG_DIR/backlog_dry_run_${START_TS}.log"
MAIN_LOG="$LOG_DIR/backlog_transcode_${START_TS}.log"
STDOUT_LOG="$LOG_DIR/backlog_stdout.log"

echo "== Step 1: dry-run =="
set +e
python "$ROOT_DIR/scripts/transcode_excel_backlog.py" \
  --dry-run \
  --log "$EXCEL_LOG"
DRY_RC=$?
set -e

if [[ $DRY_RC -ne 0 ]]; then
  echo "Dry-run failed (rc=$DRY_RC). See $EXCEL_LOG" >&2
  exit $DRY_RC
fi

NO_DB_COUNT="$(grep -c 'NO_DB ' "$EXCEL_LOG" || true)"
echo "Dry-run completed. NO_DB rows: $NO_DB_COUNT"
echo "Dry-run log: $EXCEL_LOG"

if [[ $DRY_RUN_ONLY -eq 1 ]]; then
  echo "--dry-run-only set; exiting after dry-run."
  exit 0
fi

echo "== Step 2: launch transcoding with nohup =="

set +e
nohup python "$ROOT_DIR/scripts/transcode_excel_backlog.py" \
  --verbose \
  --log "$MAIN_LOG" \
  >"$STDOUT_LOG" 2>&1 &
PID=$!
set -e

echo "Transcoding PID: $PID"
echo "Main log: $MAIN_LOG"
echo "Stdout log: $STDOUT_LOG"

echo "Waiting for PID $PID..."
set +e
wait "$PID"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "Transcoding failed (rc=$RC). See $MAIN_LOG and $STDOUT_LOG" >&2
  exit $RC
fi

echo "Transcoding completed."

if [[ $SKIP_RECONCILE -eq 0 ]]; then
  echo "== Step 3: reconcile scan =="
  : "${MP3_LIBRARY:?MP3_LIBRARY not set}"
  : "${DJ_LIBRARY:?DJ_LIBRARY not set}"
  : "${DJ_POOL_MANUAL_MP3:?DJ_POOL_MANUAL_MP3 not set}"
  : "${TAGSLUT_ARTIFACTS:?TAGSLUT_ARTIFACTS not set}"

  tools/mp3_reconcile_scan \
    --match-mode isrc \
    --roots "$MP3_LIBRARY" "$DJ_LIBRARY" "$DJ_POOL_MANUAL_MP3" \
    --out-dir "$TAGSLUT_ARTIFACTS/compare"
else
  echo "--skip-reconcile set; skipping mp3_reconcile_scan."
fi

END_SEC="$(date +%s)"
END_TS="$(timestamp)"
DUR=$((END_SEC - START_SEC))

echo "== Done =="
echo "Start:    $START_TS"
echo "End:      $END_TS"
echo "Duration: ${DUR}s"
echo "Logs:"
echo "  Dry-run: $EXCEL_LOG"
echo "  Main:    $MAIN_LOG"
echo "  Stdout:  $STDOUT_LOG"

