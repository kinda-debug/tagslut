Repository audit — suggestions for keep/archive
Date: 2025-10-26

Summary
-------
I scanned the workspace and produced a recommended classification of files into three buckets:
- Keep (active/current source & scripts)
- Archive (generated outputs, old reports, caches, backups)
- Review (manual check before action)

I also include safe commands you can run to move archived files into a dated `archive/` folder.

How I classified
----------------
Heuristics used:
- Source code (.py files at repo root that look like active tools) → Keep
- Utility shell scripts (.sh) that appear operational → Keep
- Output files (.csv, .log, .txt, _out directories, backups *.bak, __pycache__) → Archive
- Large output directories (useful_scan_out_*, near_dupe_verify_out) → Archive or compress
- Backup copies of scripts (consolidate_audio_artifacts.py.bak, .backup.*) → Archive

Files and suggested actions
---------------------------
Keep (recommended)
- dd_flac_dedupe_db.py  — main dedupe engine; keep and maintain
- repair_flacs.py       — repair helper; keep
- dedupe_swap.py, dedupe_swap_v2.py, dedupe_swap_v2_1.py — utility scripts you may still use; keep or review
- useful_scan.py, temp_audio_dedupe.py, temp_audio_dedupe_v2.py, temp_audio_dedupe_v3_1.py, preseed_flac_cache.py, verify_near_dupes.py — active utility scripts; keep
- make_broken_playlist.py — small helper; keep
- .vscode/launch.json — keep if you use VSCode
- Shell utilities that orchestrate operations: sync_any.sh, sync_music.sh, verify_quarantine.sh, verify_by_hash.sh, quarantine_corrupt.sh, quarantine_from_gemini.sh, health_scan.sh, delude_dir.sh — keep if part of your workflow

Archive (recommended)
- All CSV reports and processed output files (likely regeneratable):
  - dedupe_report_1761389493.csv
  - dedupe_report_1761394029.csv
  - dedupe_report_1761395262.csv
  - dedupe_crossformat_probe_1761394610.csv
  - dedupe_apply_1761394531.csv
  - consolidate_audio_artifacts.py.backup.110338
  - consolidate_audio_artifacts.py.bak
  - consolidated.csv
  - quarantine_verification_report.csv
  - quarantine_hash_verification.csv
  - quarantine_* and dedupe_quarantine_*.csv
  - corrupt.csv, corrupt_now.csv, dd_missing_flac.txt, live_health.csv, health_scan.log, delude_dir.log
  - similar_candidates.csv, duplicates selected by gemini.txt, out.txt.txt

- Derived output directories / caches / pyc:
  - useful_scan_out_20251025_104354/ (move/zip)
  - near_dupe_verify_out/ (move/zip)
  - __pycache__/ (safe to delete)

- Backups & large historical files
  - consolidate_audio_artifacts.py.backup.110338
  - consolidate_audio_artifacts.py.bak
  - SCR-20251025-lbfx.png.pdf (if it's a transient screenshot, consider archiving)

Review (manual check)
- dedupe_swap_v2.py, dedupe_swap_v2_1.py — two variants; keep one canonical and archive the other after verifying
- temp_audio_dedupe*.py — if some are experiments, archive older ones
- health_summary.md, SUMMARY.txt — review for useful notes; archive if captured elsewhere

Suggested safe archival commands
--------------------------------
Run these from the repository root. They will create an `archive/2025-10-26/` directory and move recommended files there. Nothing is deleted.

```bash
mkdir -p archive/2025-10-26
# Move CSVs and logs
mv *.csv archive/2025-10-26/ 2>/dev/null || true
mv *.log archive/2025-10-26/ 2>/dev/null || true
mv *.txt archive/2025-10-26/ 2>/dev/null || true
# Move backup copies and explicit historical files
mv consolidate_audio_artifacts.py.bak consolidate_audio_artifacts.py.backup.* archive/2025-10-26/ 2>/dev/null || true
# Move output directories
mv useful_scan_out_* archive/2025-10-26/ 2>/dev/null || true
mv near_dupe_verify_out archive/2025-10-26/ 2>/dev/null || true
# Move python cache
mv __pycache__ archive/2025-10-26/ 2>/dev/null || true
# Move other named historical files
mv duplicates\ selected\ by\ gemini.txt archive/2025-10-26/ 2>/dev/null || true
mv SCR-20251025-lbfx.png.pdf archive/2025-10-26/ 2>/dev/null || true

# Quick summary of archive size
du -sh archive/2025-10-26 || true
```

If you prefer compression instead of moving, use:

```bash
mkdir -p archive
tar -czvf archive/repo_archive_2025-10-26.tar.gz \
  *.csv *.log *.txt useful_scan_out_* near_dupe_verify_out consolidate_audio_artifacts.py.bak consolidate_audio_artifacts.py.backup.* __pycache__ SCR-20251025-lbfx.png.pdf 2>/dev/null || true
```

Follow-up options I can take for you
-----------------------------------
- Create and run the `archive/2025-10-26` move commands (safe, non-destructive moves). I will not delete anything; files are relocated.
- Create a compressed tarball with the archived files instead of moving.
- Produce a shorter list (dry-run) showing exactly which files would be moved (no changes).
- Implement a small `archive_unneeded.py` script that performs a more sophisticated classification (age, size, regex patterns) and optionally runs interactively for each file.

Tell me which of the follow-ups you want me to perform (dry-run list / move files / compress to tar.gz / create interactive script). If you want immediate archival, confirm and I'll execute the move commands and report results (files moved, archive size).