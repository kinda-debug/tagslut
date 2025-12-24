# Cleanup Plan

The following items are deprecated or redundant and can be removed after manual verification to keep history intact:

1. **Legacy standalone script**
   - `dd_flac_dedupe_db.py` — Deprecated in favour of the packaged `dedupe` workflows and CLI; retained only for historical reference.

2. **Archived utilities**
   - `dedupe/ARCHIVE/` (entire package) — Legacy scripts preserved for reference. Confirm no callers remain, then archive elsewhere or remove.
   - `archive/legacy_root/` — Historical assets; review and delete or move to long-term archival storage if no longer needed.

3. **Temporary patch artifacts**
   - `tmp_dedupe_patch.patch`, `tmp_full_patch_no_pyc.patch`, `tmp_missing.patch` — Temporary patch files in the repository root; safe to delete once no longer needed.
   - `docs/patches/patches/patch.patch`, `docs/patches/patches/patch_missing_files.txt`, `docs/patches/patches/patch_paths_full.txt` — Patch lists that appear to be migration scaffolding; retire after confirming no active workflows depend on them.
   - `artifacts/skipped_patch_paths.txt` — Generated helper output; remove if not referenced by automation.

4. **Outdated outputs**
   - `out/*.csv` — Sample analysis outputs; purge or relocate to `artifacts/` if still useful.

No automated deletion has been performed; these recommendations keep behaviour unchanged while highlighting clean-up opportunities.
