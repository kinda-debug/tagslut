# Progress Snapshot (2026-01-14)

## Key paths
- DB: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db`
- Artifacts: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports`
- Library root: `/Volumes/COMMUNE/M/Library`
- Staging archive: `/Volumes/COMMUNE/M/_staging__2026-01-14`
- Quarantine archive: `/Volumes/COMMUNE/M/_quarantine__2026-01-14`
- Archived keep dir: `/Volumes/COMMUNE/M/_staging__2026-01-14/2026-01-10_keep`
- Promote resume: `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/promote_by_tags.resume.json`

## Current state
- Library root has no `_staging` or `_quarantine` directories (they were moved to the archives above).
- Archived keep dir contains 0 files and 10,291 directories.
- Promote resume file shows `index=19387/19387`, last run target `/Volumes/xtralegroom`.

## Recent scans (from `scan_sessions`)
- #24 completed, `/Volumes/bad/G` zone=suspect: discovered 464, skipped 464, succeeded 0, failed 0.
- #23 completed, `/Volumes/bad/G` zone=suspect: discovered 464, skipped 0, succeeded 464, failed 0.
- #22 completed, `/Volumes/bad/G` zone=accepted: discovered 464, skipped 0, succeeded 464, failed 0.
- #21 completed, `/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep` zone=staging: discovered 21,070, skipped 14,204, succeeded 6,866, failed 0.
- #20 completed, `/Volumes/Vault/Vault` zone=suspect: discovered 2,799, skipped 0, succeeded 2,312, failed 487 (InvalidFLAC).
- #19 completed, `/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep` zone=staging: discovered 15,373, skipped 0, succeeded 15,373, failed 0.

## Dedup plan status
- `recommend_plan.json`: 20,378 groups, 76,396 decisions.
- `recommend_marked_suggestions.csv`: 70,411 rows total.
  - `bad`: KEEP 4,947, DROP 35,352
  - `COMMUNE`: KEEP 634, DROP 14,739
  - `RECOVERY_TARGET`: KEEP 14,739

## Apply/promote runs
- `apply_marked_bad.log`: last recorded progress `7500/35390` (log ends mid-run; no final summary recorded).
- `apply_marked_recovery_remaining.log`: `Summary: KEEP 0, DROP 0 (execute=True)` (all remaining already present).
- `apply_marked_vault.log`: `Summary: KEEP 739, DROP 62 (execute=True)`.
- `promote_by_tags.log` (copy mode):
  - `Summary: COPY 1284, SKIP 103, ERR 0 (execute=True)` (spillover to `/Volumes/xtralegroom`).
  - `Summary: COPY 2020, SKIP 17367, ERR 0 (execute=True)` (copy into `/Volumes/COMMUNE/M/Library`).
- `promote_by_tags_commune.log`: dry run found `total=0` after staging was archived.

## /Volumes/bad/G duplicates
- Full hash duplicates: `badG_duplicate_alerts.csv` has 0 rows.
- Streaminfo duplicates: `badG_streaminfo_alerts.csv` has 118 rows (candidates for full rehash).

## Where this stopped
- Staging and quarantine directories were archived out of the library root.
- The last promotion run completed with no remaining items under the archived keep dir.
- Next actions are either:
  - naming workflow (see `docs/NAMING_WORKFLOW.md`), or
  - spot treatment using new keep/mark cycles.
