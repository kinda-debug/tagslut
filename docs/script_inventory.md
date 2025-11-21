# Script inventory and legacy tooling

This repository now keeps all *active* automation under `dedupe/` and the
`scripts/` package. Legacy helpers, quick fixes, and shells that predate the
current CLI belong in `scripts/legacy/`, where they can be referenced or
resurrected without cluttering the repo root.

## Active `scripts/` helpers

| Script | Purpose |
| ------ | ------- |
| `scripts/best_by_hash.py` | Export candidate files by hash when comparing multiple copies of the same checksum. |
| `scripts/best_by_quality.py` | Prioritise copies of files by bitrate/sample rate when duplicates exist. |
| `scripts/best_copy.py` | Wrapper bringing the various selector heuristics together. |
| `scripts/build_new_music.py` | Provenanced build of the cleaned `NEW_MUSIC` tree from a CSV input. |
| `scripts/check_gemini_duplicates.py` | Reconciles a Gemini dupe analysis CSV with the shared `library_final.db`. |
| `scripts/gemini_reconcile_with_db.py` | Complementary Gemini reconciliation flow that mirrors canonical MUSIC locations. |
| `scripts/generate_gemini_delete_list.py` | Creates delete lists once reconciliation outputs have identified safe deletions. |
| `scripts/importos.py` | Utility for adding OS-level path mappings. |
| `scripts/move_by_csv.py` | Move files based on an input CSV (often used with best-copy outputs). |
| `scripts/per_volume_hash.py` / `scripts/per_volume_quality.py` | Assemble per-volume metadata reports. |
| `scripts/reconcile_library.py` | Higher-level workflow that coordinates scanning, matching, and manifest generation. |
| `scripts/repair_flacs.sh` et al. | Shell helpers that wrap the core Python utilities. |

> The dedicated `dedupe` CLI (invoked via `python3 -m dedupe.cli`) remains the
> canonical entry point. The `scripts/` helpers complement it when bespoke
> automation or experiments are required.

## Legacy scripts archived under `scripts/legacy/`

Each file below lives in the `scripts/legacy/` folder now. They are not
instantiated directly from the repo root but retained when historical context is
helpful. The right column summarises our decision about whether the script merits
promotion back into the primary `scripts/` package.

| Script | Status / decision |
| ------ | ----------------- |
| `build_new_music_from_global_keeps.py` | Archived (superseded by `scripts/build_new_music_from_global_keeps.py`). |
| `check_folder_status.sh` | Archived (no replacement, infrequent use). |
| `check_gemini_duplicates.py` | Archived (see `scripts/check_gemini_duplicates.py` for the refactor). |
| `clean_new_library.py` | Archived (behaviour consolidated by higher-level manifest flows). |
| `cleanup_duplicate_dbs.sh` | Archived (manual DB maintenance; not part of CLI). |
| `compare_hrm_to_library.py` | Archived (replaced by `dedupe` matching + helper utilities). |
| `db_consistency_check.sh`, `db_health_check.sh`, `db_integrity_audit.sh` | Archived (these checks are executed manually; consider a single CLI subcommand in the future). |
| `delete_gemini_dupes.py` | Archived (Gemini delete flows now live inside `scripts/gemini_reconcile_with_db.py`). |
| `find_missing_in_music.py` | Archived (legacy ad-hoc report). |
| `generate_rstudio_import(.sh)` | Archived (use `dedupe cli parse-rstudio`). |
| `move_by_hash.sh` | Archived (behaviour now handled by `scripts/move_by_csv.py` and `scripts/best_copy.py`). |
| `python3` (`merge_new_music_into_music.py`) | Archived (use `scripts/merge_new_music_into_music.py`). |
| `run_generate_upgrade_candidates.sh` | Archived (replaced by higher-level `scripts` entry points). |
| `setup.sh` | Archived (project setup lives in `README` / `docs`). |
| `verification_upgrade.py`, `verification_upgrade.py.save`, `verify_audio_integrity.sh`, `verify_manifest.sh` | Archived (ad-hoc verification scripts; a future CLI subcommand should replace them if necessary). |

## Proposed follow-up actions

1. **Document the current layout** – point readers at `scripts/` for active helpers and
   `scripts/legacy/` for archived utilities (done via this document).  Update the
   existing `README.md` / `USAGE.md` to reflect the tidied root.
2. **Consolidate manual checks** – Consider adding a `dedupe audit-db` or similar
   subcommand that reproduces the checks from the archived `db_*` shells so the
   inspection routines live inside the CLI.
3. **Evaluate high-value archives** – If we need a cleaned `NEW_MUSIC` merge flow
   or Gemini delete generator, rewrite them within `scripts/` and retire the
   legacy copies instead of keeping them around permanently.

Whenever we make behavioural changes to the CLI or these scripts, remember to
update `docs/` and the `README`/`USAGE` references so the layout stays in sync.
