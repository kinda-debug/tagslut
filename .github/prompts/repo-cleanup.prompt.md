You are Claude Code working inside the tagslut repository.

Goal:
Triage and clean up accumulated scripts, markdown files, and root-level
junk. Move dead files to archive. Delete confirmed trash. Leave active
code untouched. Produce a cleanup manifest when done.

═══════════════════════════════════════════════════════
CONTEXT: Read these first, in order
═══════════════════════════════════════════════════════

Agent instructions:
  AGENT.md
  CLAUDE.md

Roadmap (source of truth for what is active vs dead):
  docs/ROADMAP.md

═══════════════════════════════════════════════════════
OPERATING RULES
═══════════════════════════════════════════════════════

- Follow AGENT.md and CLAUDE.md in all decisions.
- Never delete a file without verifying it is not referenced in:
    .github/workflows/*.yml
    Makefile
    pyproject.toml
    any file under tagslut/ (the package)
    any file under tests/
    any active prompt under .github/prompts/
- Move dead files to the correct archive location — do not delete them.
- The only files you may delete outright are confirmed junk (see below).
- Do not touch: tagslut/ (package), tests/, tools/get*, tools/review/,
  supabase/, config/, .github/workflows/, pyproject.toml, poetry.lock.
- Produce a CLEANUP_MANIFEST.md in docs/ when done.
- Commit with: chore(cleanup): archive dead scripts and stale docs


═══════════════════════════════════════════════════════
PHASE 1 — OUTRIGHT DELETION (confirmed junk, no archive needed)
═══════════════════════════════════════════════════════

These files are either empty, editor artifacts, or MCP test files.
Verify each exists, then delete:

Root-level:
  post_task.sh                    ← Codex session artifact
  bp2tidal.py                     ← untracked one-off, no references
  build_playlist.py               ← untracked one-off, no references
  inspect_music_db.py             ← scratch diagnostic, no references
  tidal_oauth.py                  ← scratch auth script, no references
  rekordbox_v2.xml                ← old XML export, superseded by v3
  tagslut_postgres_baseline.dump  ← already in .gitignore, delete if present
  Dual-SourceTIDALBeatportMetadataFlow.md ← content already in docs/

scripts/:
  classify_tracks_sqlite_v2.patch ← already in .gitignore

Do NOT delete: AGENT.md, CLAUDE.md, README.md, CHANGELOG.md, LICENSE,
  SECURITY.md, CODEOWNERS, MANIFEST.in, Makefile, pyproject.toml,
  poetry.lock, uv.lock, .editorconfig, .flake8, .codexignore


═══════════════════════════════════════════════════════
PHASE 2 — SCRIPTS: read each file, then categorize
═══════════════════════════════════════════════════════

Archive destination: scripts/archive/

Decision rule: read the file, then check if it is referenced anywhere in
.github/workflows/, Makefile, tagslut/, or tests/. If not referenced and
its purpose is clearly one-off or superseded, move it to scripts/archive/.
If uncertain, leave it and note it in the manifest as "uncertain — left in place".

Scripts to evaluate for archiving (do NOT move without reading first):

  scripts/apply_beatport_playlist_dump_refs.py  ← one-off playlist dump
  scripts/auto_env.py                            ← check if imported anywhere
  scripts/backfill_v3_provenance_from_logs.py    ← check if still needed
  scripts/bootstrap_duration_refs_local.py       ← one-off bootstrap
  scripts/bootstrap_relink_db.py                 ← one-off relink
  scripts/capture_post_release_snapshot.py       ← one-off snapshot
  scripts/classify_tracks_sqlite.py              ← pre-v3 classifier
  scripts/extract_tracklists_from_links.py       ← one-off extract
  scripts/filter_songshift_existing.py           ← Spotify/Songshift, retired
  scripts/make_phase_v3_playlists.py             ← phase-specific, likely done
  scripts/reconcile_track_overrides.py           ← verify if still needed
  scripts/workflow_health_rescan.py              ← already in .gitignore

Scripts to keep unconditionally (do not touch):
  scripts/audit_repo_layout.py                   ← referenced in CI
  scripts/backfill_v3_identity_links.py          ← active, in roadmap
  scripts/check_cli_docs_consistency.py          ← referenced in CI
  scripts/check_hardcoded_paths.sh               ← referenced in CI
  scripts/library_export.py                      ← active
  scripts/lint_policy_profiles.py                ← active
  scripts/migrate_legacy_db.py                   ← active
  scripts/mypy_baseline_check.py                 ← referenced in CI
  scripts/push_then_post_work.sh                 ← workflow utility
  scripts/seed_dj_blocklists.py                  ← active
  scripts/transcode_m3u_to_mp3_macos.sh          ← active
  scripts/validate_v3_dual_write_parity.py       ← active


═══════════════════════════════════════════════════════
PHASE 3 — DOCS: read each file, then categorize
═══════════════════════════════════════════════════════

Archive destination: docs/archive/

Decision rule: read the file. If its content is superseded by a currently
active doc, or if it describes a completed/retired workflow with no ongoing
relevance, move it to docs/archive/. If uncertain, leave it and note it.

Docs to evaluate for archiving:

  docs/PHASE5_LEGACY_DECOMMISSION.md  ← was already a stub/redirect
  docs/DJ_REVIEW_APP.md               ← check if review app still exists in tools/
  docs/PROJECT.md                     ← check if it duplicates README.md
  docs/REDESIGN_TRACKER.md            ← check if redesign is complete
  docs/SCRIPT_SURFACE.md              ← check if accurate vs actual scripts/
  docs/SURFACE_POLICY.md              ← check if superseded by AGENT.md rules
  docs/beatport_provider_report.md    ← one-off provider report
  docs/tidal_beatport_enrichment.md   ← check if superseded by architecture docs
  CLI_HELP_PARITY_WORK_ITEM.md        ← root-level work item, check if done
  REPORT.md                           ← root-level, read and decide
  metadata.md                         ← root-level scratch, check content

Docs to keep unconditionally (do not touch):
  AGENT.md, CLAUDE.md, README.md, CHANGELOG.md
  docs/ARCHITECTURE.md
  docs/CORE_MODEL.md
  docs/DB_V3_SCHEMA.md
  docs/DJ_POOL.md
  docs/DJ_WORKFLOW.md
  docs/OPERATIONS.md
  docs/PHASE1_STATUS.md
  docs/PROGRESS_REPORT.md
  docs/ROADMAP.md
  docs/TROUBLESHOOTING.md
  docs/WORKFLOWS.md
  docs/ZONES.md


═══════════════════════════════════════════════════════
PHASE 4 — LOG MANAGEMENT
═══════════════════════════════════════════════════════

Logs do not belong in the repo. They belong alongside the epoch DB.

Check if any *.log files remain under artifacts/ or artifacts/compare/:
  find artifacts/ -name '*.log' 2>/dev/null

If any remain, move them to:
  /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/

Do not delete logs — they are enrich run records needed for the DB
size growth audit described in docs/ROADMAP.md §12.

Also check and move any *.log files loose in the repo root.

═══════════════════════════════════════════════════════
PHASE 5 — TOOLS ROOT: read each file, then categorize
═══════════════════════════════════════════════════════

Archive destination: tools/archive/

Tools to evaluate (read first, check for references in tools/get and tools/get-intake):
  tools/beatport_import_my_tracks.py  ← one-off import script
  tools/dj_review_app.py              ← check if still referenced
  tools/dj_usb_analyzer.py            ← check if active
  tools/dj_usb_incremental.py         ← check if active
  tools/dj_usb_sync.py                ← check if active
  tools/dj_usb_to_roon_m3u.py         ← check if active
  tools/fix_blocklist.py              ← check if active
  tools/inspect_api.py                ← likely scratch
  tools/add_codex_objectives.sh       ← Codex session artifact
  tools/claude-clean                  ← check what this does
  tools/get-all                       ← check if referenced anywhere
  tools/get-auto                      ← check if referenced anywhere
  tools/get-sync                      ← check if referenced anywhere

Tools to keep unconditionally (do not touch):
  tools/get, tools/get-intake, tools/get-report, tools/get-help
  tools/tiddl, tools/deemix, tools/beatport, tools/tidal
  tools/tag, tools/tag-run, tools/tag-build, tools/tag-metadata
  tools/tag-audiofeatures
  tools/tagslut, tools/playlist-sync, tools/manage-blocklist.py
  tools/_load_env.sh, tools/__init__.py
  tools/review/ (entire directory)
  tools/dj/ (entire directory)
  tools/beatportdl/ (entire directory)
  tools/rules/ (entire directory)
  tools/baselines/ (entire directory)
  tools/metadata, tools/metadata-audit, tools/metadata_scripts/


═══════════════════════════════════════════════════════
CLEANUP MANIFEST
═══════════════════════════════════════════════════════

When all phases are complete, create docs/CLEANUP_MANIFEST.md with:

  ## Deleted
  List each deleted file with one-line reason.

  ## Archived
  List each moved file with: source → destination, one-line reason.

  ## Left in place (uncertain)
  List files you were unsure about and why.

  ## Not touched (active)
  High-level summary of what was confirmed active.

═══════════════════════════════════════════════════════
COMMIT
═══════════════════════════════════════════════════════

After all phases and the manifest are complete:

  git status
  git diff --stat
  git add -A
  git commit -m "chore(cleanup): archive dead scripts, stale docs, and root junk"
  git push

Do not combine this commit with any other work.

═══════════════════════════════════════════════════════
SYNC WITH ROADMAP
═══════════════════════════════════════════════════════

After the commit, update docs/ROADMAP.md:

1. Mark §7.2 (gitignore validation) as complete if applicable.
2. Add a new entry under §7 (Repo housekeeping):
   "Script and docs cleanup: COMPLETE — see docs/CLEANUP_MANIFEST.md"
3. If any active scripts were discovered that are not yet in the roadmap,
   add them to the relevant section.

Commit the roadmap update separately:
  git add docs/ROADMAP.md docs/CLEANUP_MANIFEST.md
  git commit -m "docs: update roadmap after cleanup pass"
  git push

## ⚠ KNOWN ACTIVE SCRIPT DEPENDENCIES

Before archiving any script under scripts/, verify it is NOT referenced by:

  tools/review/pre_download_check.py   — references scripts/extract_tracklists_from_links.py
  tools/get-intake                     — references scripts/ paths via POST_MOVE_LOG
  Makefile                             — check all targets
  .github/workflows/                   — check all workflow files

scripts/extract_tracklists_from_links.py is ACTIVE — do not archive.
It is the default extract script for pre_download_check.py.
