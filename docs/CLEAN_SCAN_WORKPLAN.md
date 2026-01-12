# Clean -> Scan Playbook (Current Repo State)

This is a concrete, repeatable flow for scanning, reviewing, and applying decisions using the current paths and tooling. It emphasizes CSV-safe processing, logging, and safe resumes.

## Paths & Tools
- DB: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db`
- Reports: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/`
- Review splits: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/`
- `jq`: `/opt/homebrew/bin/jq`
- Review helpers: `tools/review/prepare_enriched.py`, `tools/review/apply_marked_actions.py`

## Cycle Overview
1) Scan a volume (resumable).
2) Recheck failures (extract exact paths).
3) Build the plan JSON.
4) Export plan CSV with header.
5) Split by prefix (CSV-safe).
6) Enrich plan and generate KEEP/DROP suggestions.
7) Apply with logging, resume, and skip-existing.
8) Verify the plan shrinks.
9) Next scan.

## 0) Health Check (per DB)
```bash
python3 tools/db/doctor.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --sessions 10
```

## 1) Scan (resumable)
Template (fill `<volume>` and `<zone>`):
```bash
python3 tools/integrity/scan.py <volume> \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone <zone> \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log
```
- Interrupt with `Ctrl+C` if needed; rerun the same command to resume (incremental skips completed files).

## 2) Recheck Failures (preserve spaces)
```bash
python3 - <<'PY'
import re
from pathlib import Path

log = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log")
out = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/failed_paths.txt")
pattern = re.compile(r"TypeError:\s*(.*?)\s*Unexpected error:")
paths = []
for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = pattern.search(line)
    if m:
        paths.append(m.group(1))
out.write_text("\n".join(paths) + "\n", encoding="utf-8")
print("Wrote", out)
PY

python3 tools/integrity/scan.py \
  --paths-from-file /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/failed_paths.txt \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone <zone> \
  --recheck --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log
```

## 3) Build the Plan
```bash
python3 tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --output /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json
```

## 4) Export and Split (CSV-safe)
Export to CSV with a header:
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

Split by prefix using CSV-aware Python (do not use grep/awk on quoted CSVs):
```bash
python3 - <<'PY'
import csv
from pathlib import Path

src = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv")
out_dir = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates")
out_dir.mkdir(parents=True, exist_ok=True)

out = {
    "COMMUNE": out_dir / "review_COMMUNE.csv",
    "RECOVERY_TARGET": out_dir / "review_RECOVERY_TARGET.csv",
    "bad": out_dir / "review_bad.csv",
    "Vault": out_dir / "review_Vault.csv",
}
prefix = {
    "COMMUNE": "/Volumes/COMMUNE/",
    "RECOVERY_TARGET": "/Volumes/RECOVERY_TARGET/",
    "bad": "/Volumes/bad/",
    "Vault": "/Volumes/Vault/",
}

with src.open(newline="") as f:
    r = csv.DictReader(f)
    writers = {k: csv.DictWriter(p.open("w", newline=""), fieldnames=r.fieldnames) for k, p in out.items()}
    for w in writers.values():
        w.writeheader()
    for row in r:
        path = row.get("path") or ""
        for k, pref in prefix.items():
            if path.startswith(pref):
                writers[k].writerow(row)
                break

print("Wrote:")
for p in out.values():
    print(" ", p)
PY
```

## 5) Enrich + Suggest (KEEP/DROP automation)
Build an enriched plan CSV by joining DB metadata (library/zone/integrity/flac_ok):
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
```

Generate suggestions:
```bash
python3 tools/review/prepare_enriched.py \
  --plan /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan_enriched.csv \
  --out-dir /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports
```

Outputs:
- `recommend_marked_suggestions.csv`
- `recommend_keep_valid.csv`
- `cross_volume_conflicts.csv`

## 6) Apply (KEEP/DROP)
Use the apply runner with logging, resume, and clean output:
```bash
python3 tools/review/apply_marked_actions.py \
  --marked /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_marked_suggestions.csv \
  --keep-dest /Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep \
  --relative-root / \
  --skip-missing \
  --execute \
  --progress-only
```
Notes:
- A log file and resume file are created next to the marked CSV (e.g., `recommend_marked_suggestions.log` and `.resume.json`).
- `--skip-existing` (default) avoids unnecessary repeats.
- Use `--no-skip-existing` only if you intentionally want to re-copy/re-delete.

## 7) Promote with canonical naming (after verification)
Dry-run first (omit `--execute`) to review the target paths.
```bash
KEEP_DIR="/Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep"
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

## 8) Verify Cleanup
- Rerun steps 3–4 and check plan size:
```bash
/opt/homebrew/bin/jq '.plan | length' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json
```
- If everything is `REVIEW`, either proceed with manual review or rerun Step 5 for new suggestions.

## 9) Next Scan (examples)
```bash
# RECOVERY_TARGET
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone accepted \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_recovery.log

# bad
python3 tools/integrity/scan.py /Volumes/bad \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone suspect \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_bad.log

# Vault
python3 tools/integrity/scan.py /Volumes/Vault/Vault \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone suspect \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_vault.log
```

## 10) Diagnostics (zoek)
Check for nested staging (JSON output):
```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path("/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep")
needle = "/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep"
matches = [str(p) for p in root.rglob("*") if p.is_dir() and str(p).startswith(needle)]
print(json.dumps({"nested_staging_dirs": matches, "count": len(matches)}, indent=2))
PY
```
Expected: `count: 0`.

## 11) Housekeeping
- Keep logs and resume files; only remove them after a verified cleanup.
- If you must reset plan outputs:
```bash
rm /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.{json,csv} \
   /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_*.csv
```
