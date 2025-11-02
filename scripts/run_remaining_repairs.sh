#!/usr/bin/env bash
# Run remaining repairs from /tmp/to_repair.txt using repair_unhealthy.py
set -euo pipefail

REPAIRS_OUT="/Volumes/dotad/MUSIC/REPAIRED/repairs_batch"
REPORT="repair_report_apply.json"
LIST="/tmp/to_repair.txt"

if [ ! -f "$LIST" ]; then
  echo "No list found at $LIST" >&2
  exit 1
fi

echo "Running repairs on list: $LIST"
python3 repair_unhealthy.py --apply --list "$LIST" --repairs-out "$REPAIRS_OUT" --report "$REPORT"

echo "Summarizing results from $REPORT"
python3 - <<'PY'
import json, sys
try:
  j = json.load(open('repair_report_apply.json'))
except Exception as e:
  print('Failed to open repair_report_apply.json:', e)
  sys.exit(2)

def has_success(entry):
  if isinstance(entry, dict):
    rep = entry.get('repair')
    return isinstance(rep, dict) and rep.get('exit_code') == 0
  return False

entries = []
if isinstance(j, dict):
  for v in j.values():
    if isinstance(v, dict):
      entries.append(v)
    elif isinstance(v, str):
      entries.append({'selected': v})
    else:
      entries.append({'selected': str(v)})
elif isinstance(j, list):
  entries = j
else:
  entries = [j]

ok = sum(1 for e in entries if has_success(e))
fail = sum(1 for e in entries if not has_success(e))
print('successful repairs:', ok, 'failed/missing:', fail)
PY

echo "Done. Inspect $REPORT and $REPAIRS_OUT/logs for details."
