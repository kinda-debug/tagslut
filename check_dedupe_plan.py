#!/usr/bin/env bash
# Root shim: forward to canonical script in scripts/
exec python3 "$(dirname "$0")/scripts/check_dedupe_plan.py" "$@"