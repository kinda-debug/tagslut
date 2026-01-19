# Handover - Dedupe Recovery Workflow

This document summarizes the current state, key paths, and the non-looping workflow for audit continuity.

## Purpose
Maintain an evidence-first dedupe workflow across multiple volumes, stage approved KEEP files, and promote them into the canonical library with deterministic naming.

## Key Paths (Authoritative)
- Repo: `/Users/georgeskhawam/Projects/dedupe`
- Database: `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-09/music.db`
- Artifacts (plans/logs): `/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports`
- Candidates (review CSVs): `/Users/georgeskhawam/Projects/dedupe/artifacts/M/01_candidates`
- Canonical library: `/Volumes/COMMUNE/M/Library`
- Staging keep (current): `/Volumes/COMMUNE/M/Library/_staging/2026-01-10_keep`
- Source volumes:
  - `/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY`
  - `/Volumes/bad`
  - `/Volumes/Vault/Vault`

## Current State Snapshot (last recorded)
- Staging scan complete (Session 21): 6,866 succeeded, 0 failed.
- Recommend plan export produced `recommend_plan.csv` with 71,214 lines (includes header).
- Split counts from `recommend_plan.csv` (includes header):
  - COMMUNE: 15,374
  - RECOVERY_TARGET: 14,740
  - bad: 40,301
  - Vault: 802
- Vault review actions observed: 801 `REVIEW`.

If you need the latest counts, re-run the split step in `docs/SCAN_TO_REVIEW_WORKFLOW.md`.

## Audit Evidence (Files to Preserve)
- Plan:
  - `artifacts/M/03_reports/recommend_plan.json`
  - `artifacts/M/03_reports/recommend_plan.csv`
  - `artifacts/M/03_reports/recommend_plan_enriched.csv`
- Suggestions:
  - `artifacts/M/03_reports/recommend_marked_suggestions.csv`
  - `artifacts/M/03_reports/recommend_keep_valid.csv`
  - `artifacts/M/03_reports/cross_volume_conflicts.csv`
- Apply logs/resume:
  - `artifacts/M/03_reports/recommend_marked_suggestions.log`
  - `artifacts/M/03_reports/recommend_marked_suggestions.resume.json`
- Promote logs/resume:
  - `artifacts/M/03_reports/promote_by_tags.log`
  - `artifacts/M/03_reports/promote_by_tags.resume.json`
- Scan logs:
  - `artifacts/M/03_reports/scan_errors_*.log`

## Canonical Naming (Promotion Rules)
Promotion uses `tools/review/promote_by_tags.py` and reads FLAC tags only.
Rules applied (per your Picard template):
- Top folder: `label` if compilation, else `albumartist` or `artist`.
- Album folder: `(YYYY) Album` plus suffix `[Bootleg]`, `[Live]`, `[Compilation]`, `[Soundtrack]`, `[EP]`, `[Single]` as applicable.
- Filename: `NN. ` + `Artist - ` (if compilation) + title with `featuring`/`ft.` normalized to `feat.`.
Fallbacks are used when tags are missing (e.g., `Unknown Artist`, `Unknown Album`).

## Loop Guardrails (No Endless Re-runs)
- Keep a single `KEEP_DIR` constant for apply -> staging scan -> promote.
- Do not rebuild the plan unless:
  - You ran a new scan, or
  - You intentionally changed files.
- Resume by re-running the exact same command; logs and resume files prevent restarts.

## Reference Workflow (Short Form)
The canonical steps are documented in:
- `docs/SCAN_TO_REVIEW_WORKFLOW.md` (full sequence)
- `docs/CLEAN_SCAN_WORKPLAN.md` (detailed playbook)
- `docs/QUICKSTART.md` (daily run)

## Common Failure Modes
- Missing/mounted volumes: apply/promote will skip missing sources if `--skip-missing` is enabled (default).
- Nested staging paths: always use `--skip-existing` (default) and keep `KEEP_DIR` fixed.
- CSV split errors: use the CSV-safe split in `docs/SCAN_TO_REVIEW_WORKFLOW.md` (not raw `awk`).

## Next Actions (If Continuing)
1) Verify `recommend_marked_suggestions.log` and resume state.
2) Confirm staging scan results.
3) Promote from staging into `/Volumes/COMMUNE/M/Library` using `promote_by_tags.py`.
4) Archive the logs and plans for audit.
