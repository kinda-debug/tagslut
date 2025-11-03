#!/usr/bin/env bash
# Root shim: forward to canonical script in scripts/
exec python3 "$(dirname "$0")/scripts/apply_dedupe_plan.py" "$@"
