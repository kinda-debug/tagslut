# Scan-to-Review (FINAL_LIBRARY First)

Goal: finish `/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY` once with full evidence, recheck only its failures, generate the plan, and stage healthy tracks. Defer other volumes until later.

## 0) Health Check (once)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/db/doctor.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db"
```

## 1) Scan FINAL_LIBRARY (one thorough pass)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/integrity/scan.py \
  /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone accepted \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_final_library.log
```

## 2) Recheck only failed paths from that scan (preserve spaces)
```
python3 - <<'PY'
import re
from pathlib import Path

log = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_final_library.log")
out = Path("/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/failed_paths_final_library.txt")
pattern = re.compile(r"TypeError:\s*(.*?)\s*Unexpected error:")
paths = []
for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
    m = pattern.search(line)
    if m:
        paths.append(m.group(1))
out.write_text("\n".join(paths) + "\n", encoding="utf-8")
print("Wrote", out)
PY

python3 /Users/georgeskhawam/Projects/dedupe/tools/integrity/scan.py \
  --paths-from-file /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/failed_paths_final_library.txt \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone accepted \
  --recheck --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_final_library.log
```

## 3) Generate plan (after FINAL_LIBRARY is complete)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --output /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json
```

## 4) Export CSV with header
```
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

## 5) Split by prefix (CSV-safe)
```
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

## 6) Prepare suggestions and apply (optional automation)
- Enrich the plan with DB metadata and run `tools/review/prepare_enriched.py` (see `docs/CLEAN_SCAN_WORKPLAN.md`).
- Apply KEEP/DROP with logging + resume:
```
KEEP_DIR="/Volumes/COMMUNE/M/Library/_staging/$(date +%F)_keep"
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/apply_marked_actions.py \
  --marked /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_marked_suggestions.csv \
  --keep-dest "$KEEP_DIR" \
  --relative-root / \
  --skip-missing \
  --execute \
  --progress-only
```
Notes:
- A log file and resume file are created next to the marked CSV unless you override `--log-file` or `--resume-file`.
- `--skip-existing` (default) avoids unnecessary repeats; use `--no-skip-existing` only if you want to re-copy.

## 7) Stage healthy tracks
- Scan the staging folder once to ingest new paths:
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/integrity/scan.py \
  "$KEEP_DIR" \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone staging \
  --check-integrity --check-hash --incremental \
  --error-log /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors_staging.log
```

## 8) Promote with canonical naming (after verification)
Dry-run first (omit `--execute`) to inspect the paths.
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/promote_by_tags.py \
  --source-root "$KEEP_DIR" \
  --dest-root /Volumes/COMMUNE/M/Library \
  --mode move \
  --execute \
  --progress-only
```
Notes:
- Log and resume files are written under `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/`.
- Re-run the same command to resume after interruption.
- Keep `KEEP_DIR` constant for steps 6–8 to avoid accidental restarts.

## Removal policy (approved, quarantine-first)
- Zone priority: `accepted > staging > suspect > quarantine`
- Tier 1 - Auto-remove (quarantine then delayed delete):
  - Same SHA256 (bit-identical).
  - Keeper is valid (`integrity_state=valid` AND `flac_ok=1`) in a higher-priority zone.
- Tier 2 - Quarantine only:
  - Same SHA256, but keeper is corrupt or `flac_ok=0`.
  - Same SHA256, but keeper only in suspect (no accepted/staging keeper).
- Tier 3 - Manual review only:
  - Streaminfo-only matches or any non-SHA256 identity.
- Retention window: 30 days (default).
- /Volumes/bad/G override: not enabled by default; only via explicit opt-in flag and logged in the plan.

### Plan removals (dry-run, DB-backed)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/plan_removals.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --output /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/removal_plan.csv
```

### Apply quarantine (no deletes)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/apply_removals.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --plan /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/removal_plan.csv \
  --quarantine-root /Volumes/COMMUNE/M/_quarantine \
  --execute \
  --progress-only
```

### Delete after retention (explicit phase)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/review/apply_removals.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --delete-after-days 30 \
  --execute \
  --progress-only
```

## 9) Defer everything else
- Skip scanning other volumes until FINAL_LIBRARY + staging are done.
- When ready, repeat the same pattern per volume. For full detail, see `docs/CLEAN_SCAN_WORKPLAN.md`.

Keep all outputs under `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/` (logs, plans) and `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/` (per-prefix review CSVs).
