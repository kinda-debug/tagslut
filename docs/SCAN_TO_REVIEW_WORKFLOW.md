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
  --error-log /Volumes/COMMUNE/M/03_reports/scan_errors_final_library.log
```

## 2) Recheck only failed paths from that scan
```
grep 'TypeError' /Volumes/COMMUNE/M/03_reports/scan_errors_final_library.log \
  > /Volumes/COMMUNE/M/03_reports/failed_paths_final_library.log
awk '{print $NF}' /Volumes/COMMUNE/M/03_reports/failed_paths_final_library.log \
  > /Volumes/COMMUNE/M/03_reports/failed_paths_final_library.txt

python3 /Users/georgeskhawam/Projects/dedupe/tools/integrity/scan.py \
  --paths-from-file /Volumes/COMMUNE/M/03_reports/failed_paths_final_library.txt \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --zone accepted \
  --recheck --check-integrity --check-hash --incremental \
  --error-log /Volumes/COMMUNE/M/03_reports/scan_errors_final_library.log
```

## 3) Generate plan (after FINAL_LIBRARY is complete)
```
python3 /Users/georgeskhawam/Projects/dedupe/tools/decide/recommend.py \
  --db "/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db" \
  --output /Volumes/COMMUNE/M/03_reports/recommend_plan.json
```

Export CSV for review:
```
/usr/local/bin/jq -r '
  .plan[] as $g |
  $g.decisions[] |
  [
    $g.group_id,
    .path,
    .action,
    .reason,
    .confidence,
    .evidence.conflict_label,
    .evidence.risk_delta.duration_diff,
    .evidence.risk_delta.bitrate_diff
  ] | @csv
' /Volumes/COMMUNE/M/03_reports/recommend_plan.json \
> /Volumes/COMMUNE/M/03_reports/recommend_plan.csv
```

## 4) Split by prefix for manual review
```
grep '^/Volumes/COMMUNE' /Volumes/COMMUNE/M/03_reports/recommend_plan.csv > /Volumes/COMMUNE/M/01_candidates/review_COMMUNE.csv
grep '^/Volumes/Vault'   /Volumes/COMMUNE/M/03_reports/recommend_plan.csv > /Volumes/COMMUNE/M/01_candidates/review_Vault.csv
grep '^/Volumes/bad'     /Volumes/COMMUNE/M/03_reports/recommend_plan.csv > /Volumes/COMMUNE/M/01_candidates/review_bad.csv
```

## 5) Optional: Excel
```
python3 /Users/georgeskhawam/Projects/dedupe/convert_paths_to_excel.py \
  /Volumes/COMMUNE/M/01_candidates/review_COMMUNE.csv \
  /Volumes/COMMUNE/M/01_candidates/review_COMMUNE.xlsx
```

## 6) Stage healthy tracks
- Copy vetted FINAL_LIBRARY tracks into `/Volumes/COMMUNE/M/Library/_staging/$(date +%F)` (copy only).
- Scan the staging folder once to ingest new paths (same `scan.py` with `--zone staging`, `--check-integrity/--check-hash`, and an `--error-log`).
- After staging is vetted, promote manually into `/Volumes/COMMUNE/M/Library`.

## 7) Defer everything else
- Skip scanning other volumes until FINAL_LIBRARY + staging are done.
- When ready, repeat the same pattern per volume: one thorough scan + recheck failures, then update the plan.

Keep all outputs under `/Volumes/COMMUNE/M/03_reports/` (logs, plans) and `/Volumes/COMMUNE/M/01_candidates/` (per-prefix review CSVs) for auditability.
