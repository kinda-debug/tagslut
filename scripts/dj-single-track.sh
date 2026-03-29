#!/usr/bin/env bash
# Lightweight helper that runs the canonical 4-stage DJ pipeline for a single provider URL.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: $0 [--verbose] [--debug-raw] [--no-precheck] [--xml-out <path>] <provider-url>

Runs intake, MP3 build, dj backfill, and dj validate for the supplied provider URL
and the environment defined by $TAGSLUT_DB and $DJ_LIBRARY. If --xml-out is
provided, emits Rekordbox XML after validation.
EOF
}

XML_OUT=""
URL=""
VERBOSE=false
DEBUG_RAW=false
NO_PRECHECK=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --xml-out)
      [[ $# -ge 2 ]] || { echo "Error: --xml-out requires a file path" >&2; usage; exit 1; }
      XML_OUT="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --debug-raw)
      DEBUG_RAW=true
      shift
      ;;
    --no-precheck)
      NO_PRECHECK=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "$URL" ]]; then
        echo "Error: unexpected extra argument: $1" >&2
        usage
        exit 1
      fi
      URL="$1"
      shift
      ;;
  esac
done

if [[ -z "$URL" ]]; then
  echo "Error: provider URL required" >&2
  usage
  exit 1
fi

if [[ -z "${TAGSLUT_DB:-}" ]]; then
  echo "TAGSLUT_DB is not set. Export it to point at your tagslut FRESH DB." >&2
  exit 1
fi

if [[ -z "${DJ_LIBRARY:-}" ]]; then
  echo "DJ_LIBRARY is not set. Export it so the DJ MP3 build knows where to write." >&2
  exit 1
fi

if [[ ! -d "$DJ_LIBRARY" ]]; then
  echo "DJ_LIBRARY directory not found: $DJ_LIBRARY" >&2
  exit 1
fi

INTAKE_ARGS=(poetry run tagslut intake url --db "$TAGSLUT_DB")
DJ_VALIDATE_ARGS=(poetry run tagslut dj validate --db "$TAGSLUT_DB")
if [[ "$VERBOSE" == true ]]; then
  INTAKE_ARGS+=(--verbose)
  DJ_VALIDATE_ARGS+=(-v)
fi
if [[ "$DEBUG_RAW" == true ]]; then
  INTAKE_ARGS+=(--debug-raw)
fi
if [[ "$NO_PRECHECK" == true ]]; then
  INTAKE_ARGS+=(--no-precheck)
fi

run_step() {
  printf "\n→ %s\n" "$*"
  if ! "$@"; then
    echo "Command failed: $*" >&2
    exit 1
  fi
}

run_intake_attempt() {
  printf "\n→ %s\n" "$*"
  "$@"
}

if ! run_intake_attempt "${INTAKE_ARGS[@]}" "$URL"; then
  if [[ "$NO_PRECHECK" == false ]]; then
    echo "Intake failed during precheck; retrying once with --no-precheck." >&2
    echo "If the first failure was TIDAL precheck auth (for example tidal_token_missing), the retry bypasses that gate." >&2
    if ! run_intake_attempt "${INTAKE_ARGS[@]}" --no-precheck "$URL"; then
      echo "Command failed: ${INTAKE_ARGS[*]} --no-precheck $URL" >&2
      exit 1
    fi
  else
    echo "Command failed: ${INTAKE_ARGS[*]} $URL" >&2
    exit 1
  fi
fi
run_step poetry run tagslut mp3 build --db "$TAGSLUT_DB" --dj-root "$DJ_LIBRARY" --execute
run_step poetry run tagslut dj backfill --db "$TAGSLUT_DB" --execute
run_step "${DJ_VALIDATE_ARGS[@]}"

if [[ -n "$XML_OUT" ]]; then
  run_step poetry run tagslut dj xml emit --db "$TAGSLUT_DB" --out "$XML_OUT"
fi

printf "\n✓ DJ pipeline complete for %s\n" "$URL"
