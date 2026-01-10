# Clean → Scan Playbook (Current Repo State)

This is a concrete, repeatable flow for reviewing duplicates and running future scans using your current paths and tooling. It supersedes ad hoc notes and is aligned with the current DB/artifact layout.

## Paths & Tools
- DB: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db`
- Reports: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/`
- Review splits: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/`
- `jq`: `/opt/homebrew/bin/jq`

## Cycle Overview
1) **Scan** a volume with integrity + hash (resumable).
2) **Recheck** failures (only if `scan_errors.log` has entries).
3) **Plan**: generate duplicates, export CSV, split by prefix.
4) **Review**: prioritize cross-volume conflicts; mark KEEP/DROP.
5) **Apply**: move/delete/quarantine reviewed items (script once decisions are marked).
6) **Verify**: rerun plan to confirm the backlog shrinks.
7) **Next Scan**: repeat for the next volume/zone.

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

## 2) Recheck Failures (only if errors exist)
```bash
grep 'TypeError' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/scan_errors.log \
  | sed -E 's/^TypeError: (.*) Unexpected error:.*/\1/' \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/failed_paths.txt

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

## 4) Export and Split
Export to CSV:
```bash
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
    .evidence.risk_delta.bit_depth_diff
  ] | @csv
' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv
```

Split by prefix (edit/add prefixes as needed):
```bash
grep '^/Volumes/bad' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_bad.csv

grep '^/Volumes/RECOVERY_TARGET' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_RECOVERY_TARGET.csv

grep '^/Volumes/COMMUNE' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_COMMUNE.csv

grep '^/Volumes/Vault' /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.csv \
  > /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_Vault.csv
```

## 5) Review Guidance (what to focus on)
- Start with **cross-volume groups**: same `group_id` present in both `/Volumes/RECOVERY_TARGET` and `/Volumes/bad`. Keep FINAL_LIBRARY/accepted copies; drop or quarantine the bad copies.
- All current conflicts are `conflict_label=BIT_IDENTICAL` with no duration/bitrate deltas, so prefer the higher-trust location/zone.
- Work in batches: split large CSVs into smaller chunks (e.g., 5k rows) and add a `decision_note` column (KEEP/DROP/REVIEW) as you review.

## 6) Apply (after decisions are marked)
- Current `apply.py` is tally-only (`--dry-run` by default). Once you have marked decisions, we can script a mover/deleter to act on DROP/KEEP. Until then, use:
```bash
python3 tools/decide/apply.py \
  /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json \
  --dry-run
```

## 7) Verify Cleanup
- After removing/quarantining reviewed items, rerun steps 3–4 to confirm `groups_count` drops and the split CSVs shrink.

## 8) Next Scan
- Pick the next volume/zone and rerun the scan template (Step 1). Incremental mode resumes if interrupted. Use a distinct error log per run, e.g., `scan_errors_next.log`.

## 9) Housekeeping
- To clear old artifacts before regenerating:
```bash
rm /Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.{json,csv} \
   /Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_*.csv
```
- Keep `scan_errors.log` for audit unless you’ve copied its contents elsewhere.

## Where You Are Now
- Scans complete for FINAL_LIBRARY and `/Volumes/bad`; DB is current.
- Active review files:
  - `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_bad.csv` (~40k rows)
  - `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates/review_RECOVERY_TARGET.csv` (~14k rows)
- COMMUNE/Vault splits are empty because no entries matched those prefixes in the latest plan.
