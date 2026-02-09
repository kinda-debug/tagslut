# tools/review

Active operational scripts for dedupe planning, analysis, and move execution.

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
- `normalize_genres.py`
- `tag_normalized_genres.py`
- `dump_file_tags.py`
- `music_tags_scan_and_strip.py`

## Historical Snapshots

`promote_by_tags_versions/` contains historical script snapshots retained for traceability.

## Policy

- Keep operations move-only unless a script is explicitly analysis-only.
- New scripts should include a short usage header and write outputs to `artifacts/`.
