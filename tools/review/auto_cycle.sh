#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DB="/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"
OUT_DIR="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports"
JQ="/opt/homebrew/bin/jq"
KEEP_DEST="/Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep"
MARKED=""
PROGRESS_EVERY=500
APPLY=0
LOG_FILE=""
RESUME_FILE=""

usage() {
  cat <<'USAGE'
Usage: tools/review/auto_cycle.sh [options]

Options:
  --db PATH            DB path (default: /Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db)
  --out-dir DIR        Reports directory (default: /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports)
  --keep-dest DIR      Staging destination (default: /Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep)
  --marked PATH        Marked suggestions CSV (default: <out-dir>/recommend_marked_suggestions.csv)
  --progress-every N   Progress interval (default: 500)
  --apply              Apply KEEP/DROP after generating suggestions
  --no-apply           Skip apply step (default)
  --log-file PATH      Log file for apply step (default: <marked>.log)
  --resume-file PATH   Resume file for apply step (default: <marked>.resume.json)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db) DB="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --keep-dest) KEEP_DEST="$2"; shift 2;;
    --marked) MARKED="$2"; shift 2;;
    --progress-every) PROGRESS_EVERY="$2"; shift 2;;
    --apply) APPLY=1; shift;;
    --no-apply) APPLY=0; shift;;
    --log-file) LOG_FILE="$2"; shift 2;;
    --resume-file) RESUME_FILE="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

mkdir -p "$OUT_DIR"

PLAN_JSON="$OUT_DIR/recommend_plan.json"
PLAN_CSV="$OUT_DIR/recommend_plan.csv"
PLAN_ENRICHED="$OUT_DIR/recommend_plan_enriched.csv"
MARKED="${MARKED:-$OUT_DIR/recommend_marked_suggestions.csv}"
LOG_FILE="${LOG_FILE:-${MARKED}.log}"
RESUME_FILE="${RESUME_FILE:-${MARKED}.resume.json}"

if [[ ! -x "$JQ" ]]; then
  echo "jq not found at $JQ"
  exit 1
fi

echo "[1/4] recommend -> $PLAN_JSON"
python3 tools/decide/recommend.py --db "$DB" --output "$PLAN_JSON"

echo "[2/4] export CSV -> $PLAN_CSV"
{
  echo "group_id,path,action,reason,confidence,conflict_label,duration_diff,bitrate_diff,sample_rate_diff,bit_depth_diff,integrity_state,flac_ok"
  "$JQ" -r '
    .plan[] as $g | $g.decisions[] |
    [
      $g.group_id,
      .path,
      .action,
      .reason,
      .confidence,
      .evidence.conflict_label,
      .evidence.risk_delta.duration_diff,
      .evidence.risk_delta.bitrate_diff,
      .evidence.risk_delta.sample_rate_diff,
      .evidence.risk_delta.bit_depth_diff,
      .integrity_state,
      .flac_ok
    ] | @csv
  ' "$PLAN_JSON"
} > "$PLAN_CSV"

echo "[3/4] enrich -> $PLAN_ENRICHED"
DB="$DB" SRC="$PLAN_CSV" OUT="$PLAN_ENRICHED" python3 - <<'PY'
import csv, os, sqlite3
from pathlib import Path

db = os.environ["DB"]
src = Path(os.environ["SRC"])
out = Path(os.environ["OUT"])

conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT path, library, zone, integrity_state, flac_ok FROM files")
meta = {p: (lib, zone, integ, flac) for p, lib, zone, integ, flac in cur.fetchall()}

header = [
    "group_id","path","library","zone","action","reason","confidence","conflict_label",
    "duration_diff","bitrate_diff","sample_rate_diff","bit_depth_diff","integrity_state","flac_ok",
]

with src.open(newline="") as f, out.open("w", newline="") as o:
    r = csv.DictReader(f)
    w = csv.DictWriter(o, fieldnames=header)
    w.writeheader()
    for row in r:
        path = row.get("path") or ""
        lib, zone, integ, flac = meta.get(path, (None, None, None, None))
        w.writerow({
            "group_id": row.get("group_id",""),
            "path": path,
            "library": lib,
            "zone": zone,
            "action": row.get("action",""),
            "reason": row.get("reason",""),
            "confidence": row.get("confidence",""),
            "conflict_label": row.get("conflict_label",""),
            "duration_diff": row.get("duration_diff",""),
            "bitrate_diff": row.get("bitrate_diff",""),
            "sample_rate_diff": row.get("sample_rate_diff",""),
            "bit_depth_diff": row.get("bit_depth_diff",""),
            "integrity_state": integ,
            "flac_ok": "True" if flac == 1 else "False" if flac == 0 else "",
        })
print("Wrote", out)
PY

echo "[4/4] suggestions -> $OUT_DIR"
python3 tools/review/prepare_enriched.py --plan "$PLAN_ENRICHED" --out-dir "$OUT_DIR"

if [[ "$APPLY" -eq 1 ]]; then
  echo "[apply] marked=$MARKED keep_dest=$KEEP_DEST"
  python3 tools/review/apply_marked_actions.py \
    --marked "$MARKED" \
    --keep-dest "$KEEP_DEST" \
    --relative-root / \
    --skip-missing \
    --execute \
    --progress-only \
    --progress-every "$PROGRESS_EVERY" \
    --log-file "$LOG_FILE" \
    --resume-file "$RESUME_FILE"
else
  echo "[done] Suggestions ready. Re-run with --apply to execute KEEP/DROP."
fi
