# Quickstart (Daily Run)

Use this when you just want to scan, plan, suggest, and apply with minimal steps.

## One-command automation (plan -> suggestions -> optional apply)
```bash
tools/review/auto_cycle.sh --apply
```
Notes:
- Uses defaults from the playbook (DB, reports dir, jq path).
- Writes logs/resume files next to the marked CSV.
- Use `--no-apply` to stop after generating suggestions.

## 1) Scan a volume (resumable)
```bash
python3 tools/integrity/scan.py <volume> \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone <zone> \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log
```

## 2) Build the plan
```bash
python3 tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --output /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json
```

## 3) Export CSV with a header
```bash
{
  echo "group_id,path,action,reason,confidence,conflict_label,duration_diff,bitrate_diff,sample_rate_diff,bit_depth_diff,integrity_state,flac_ok"
  /opt/homebrew/bin/jq -r '
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
  ' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json
} > /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv
```

## 4) Enrich and generate suggestions
```bash
python3 - <<'PY'
import csv, sqlite3
from pathlib import Path

db = "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"
src = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv")
out = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan_enriched.csv")

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

python3 tools/review/prepare_enriched.py \
  --plan /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan_enriched.csv \
  --out-dir /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports
```

## 5) Apply KEEP/DROP (clean output + resume)
```bash
KEEP_DIR="/Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep"
python3 tools/review/apply_marked_actions.py \
  --marked /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_marked_suggestions.csv \
  --keep-dest "$KEEP_DIR" \
  --relative-root / \
  --skip-missing \
  --execute \
  --progress-only
```
Notes:
- Log file and resume file are created next to the marked CSV.
- Interrupt with Ctrl+C, rerun the same command to resume.
- Keep `KEEP_DIR` constant for steps 5–7 to avoid accidental restarts.

## 6) Stage scan (optional verification)
```bash
python3 tools/integrity/scan.py "$KEEP_DIR" \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone staging \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_staging.log
```

## 7) Promote with canonical naming (after verification)
Dry-run first (omit `--execute`) to review the target paths.
```bash
python3 tools/review/promote_by_tags.py \
  --source-root "$KEEP_DIR" \
  --dest-root /Volumes/COMMUNE/M/Library \
  --mode move \
  --execute \
  --progress-only
```
Notes:
- Log and resume files are written under `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/`.
- Re-run the same command to resume after interruption.

## Loop guardrails
- Rebuild the plan (steps 2–4) only after new scans or after you intentionally changed files.
- Resume apply/promote by rerunning the exact same command; do not rotate `KEEP_DIR` mid-run.
