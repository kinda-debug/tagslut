# tools/review

Active operational scripts for tagslut planning, analysis, and move execution.

## Core Move Workflow

1. Build a plan:
- `plan_promote_to_final_library.py`
- `plan_fpcalc_*` planners
- `plan_move_skipped_to_fix.py`

2. Review and summarize:
- `plan_summary.py`
- `recommend_plan_to_moves.py`
- `audio_dupe_audit.py`
- `fingerprint_report.py`
- `isrc_dupes_report.py`

3. Execute move-only actions:
- `move_from_plan.py`
- `quarantine_from_plan.py`
- `promote_by_tags.py` (direct promotion path; use `--move-log` for JSONL move audit output)

4. Sync DB after moves:
- `apply_moves_log_to_db.py`

## Metadata/Tag Helpers

- `scan_with_trust.py`
- `hoard_tags.py`
- `canonize_tags.py`
- `process_unmatched_by_tags.py` — fast tag-only folder triage against DB; outputs matched/unmatched lists, writes a resumable tracker, and can run a processing command only for unmatched files
- **Genre Normalization (synergistic):**
  - `normalize_genres.py` — Normalize genre/style tags and backfill DB with canonical values
  - `tag_normalized_genres.py` — Apply normalized genre/style tags in-place to FLAC files
  - Both use shared `GenreNormalizer` class for consistent tag processing
  - See `docs/WORKFLOWS.md` Workflow 9 for usage guide
  - Rules format: `tools/rules/genre_normalization.json` (Beatport-compatible mappings)
- `dump_file_tags.py`
- `music_tags_scan_and_strip.py`

## Historical Snapshots

`promote_by_tags_versions/` contains historical script snapshots retained for traceability.

## Policy

- Keep operations move-only unless a script is explicitly analysis-only.
- New scripts should include a short usage header and write outputs to `artifacts/`.

## Quick Usage: Process Unmatched By Tags

```bash
# Scan folder quickly by tags and write matched/unmatched manifests
python tools/review/process_unmatched_by_tags.py \
  /path/to/incoming \
  --db "$TAGSLUT_DB" \
  --out-dir artifacts/tag_triage

# Process only unmatched files (foreground, visible output, resumable)
python tools/review/process_unmatched_by_tags.py \
  /path/to/incoming \
  --db "$TAGSLUT_DB" \
  --process-cmd 'poetry run tagslut index register "{path}" --source staging --execute -v' \
  --tracker-file artifacts/tag_triage/my_run_tracker.json

# Force a clean run (ignore previous tracker cache)
python tools/review/process_unmatched_by_tags.py \
  /path/to/incoming \
  --db "$TAGSLUT_DB" \
  --process-cmd 'poetry run tagslut index register "{path}" --source staging --execute -v' \
  --reset-tracker

# Add promotion eligibility diagnostics for unmatched files
python tools/review/process_unmatched_by_tags.py \
  /path/to/incoming \
  --db "$TAGSLUT_DB" \
  --promotion-report \
  --promotion-verify-flac
```

Notes:
- Output is split into clear stages: DB index load, triage, processing, and promotion report.
- A tracker JSON is written by default to `<out-dir>/tag_triage_tracker.json`.
- Resume is enabled by default; already-triaged and already-processed files are skipped when file `size` and `mtime` are unchanged.
- Use `--no-resume` to disable cache/resume behavior for a run.
