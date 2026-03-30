## Deleted

- `rekordbox_v2.xml` (filename previously had a trailing space character) — legacy root export artifact superseded by v3 export flow.

## Archived

- `scripts/extract_tracklists_from_links.py` -> `scripts/archive/extract_tracklists_from_links.py` — unreferenced one-off extraction utility.
- `artifacts/intake/logs/get_intake_20260322_114441.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_114441.log` — runtime log moved out of repo per log policy.
- `artifacts/intake/logs/get_intake_20260322_115403.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_115403.log` — runtime log moved out of repo per log policy.
- `artifacts/intake/logs/get_intake_20260322_115957.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_115957.log` — runtime log moved out of repo per log policy.
- `artifacts/intake/logs/get_intake_20260322_120301.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_120301.log` — runtime log moved out of repo per log policy.
- `artifacts/intake/logs/get_intake_20260322_120429.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_120429.log` — runtime log moved out of repo per log policy.
- `artifacts/intake/logs/get_intake_20260322_120540.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/get_intake_20260322_120540.log` — runtime log moved out of repo per log policy.
- `artifacts/compare/post_move_enrich_art_20260322_140014.log` -> `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/post_move_enrich_art_20260322_140014.log` — runtime log moved out of repo per log policy.

## Left in place (uncertain)

- `scripts/auto_env.py` — no required-location references found; plausible local environment bootstrap helper.
- `scripts/reconcile_track_overrides.py` — no required-location references found; still targets live `config/dj/track_overrides.csv` data.
- `tools/fix_blocklist.py` — no required-location references found; appears to be a still-useful maintenance utility.
- `tools/get-all` — no required-location references found; large orchestration wrapper that may still be used manually.
- `tools/get-auto` — no required-location references found and not wired from `tools/get`/`tools/get-intake`, but may still be used as a manual helper.
- `tools/get-sync` — deprecated alias, but still mentioned by `tools/get` help text.
- `tools/claude-clean` — no required-location references found; wrapper to `tools/review/claude_clean.py`, unclear current operator usage.
- `REPORT.md` — no required-location references found; root strategy doc still reads as current-state project documentation.

## Not touched (active)

- Confirmed active docs retained: `docs/DJ_REVIEW_APP.md`, `docs/PROJECT.md`, `docs/REDESIGN_TRACKER.md`, `docs/SCRIPT_SURFACE.md`, `docs/SURFACE_POLICY.md`, `docs/PHASE5_LEGACY_DECOMMISSION.md`.
- Confirmed active scripts retained: `scripts/backfill_v3_provenance_from_logs.py` (Makefile/tests references), `scripts/capture_post_release_snapshot.py` (tests reference).
- Confirmed active tools retained: `tools/dj_review_app.py` (called by `tagslut/cli/commands/dj.py`), `tools/dj_usb_sync.py` (referenced by `tagslut/_web/review_app.py`).
- Confirmed absent from this repository snapshot (already cleaned earlier): `post_task.sh`, `bp2tidal.py`, `build_playlist.py`, `inspect_music_db.py`, `tidal_oauth.py`, `tagslut_postgres_baseline.dump`, `Dual-SourceTIDALBeatportMetadataFlow.md`, `scripts/classify_tracks_sqlite_v2.patch`.

## 2026-03-29 supplement cleanup pass

### Phase A — root junk

Deleted (no required-location references found):

- `qqqq.txt`
- `sdf.dc`
- `claudebs.md`
- `tagslut_DIRECTIVES_REVISED_2026-03-26.md`
- `DJ_PIPELINE_FULL_REPAIR_CODEX.md`
- `POSTMAN_AI_PROMPT.md`
- `postman-fix-prompt.md`
- `20260317_rekordbox.xml`

### Phase B — duplicate `process_dedupe.py`

- Removed root-level `process_dedupe.py` duplicate (no required-location references found); kept canonical `scripts/process_dedupe.py`.

### Phase C — `files/` scratch directory

- Moved `files/BACKFILL_GUIDE.md` -> `docs/BACKFILL_GUIDE.md`.
- Moved `files/PROVENANCE_INTEGRATION.md` -> `docs/PROVENANCE_INTEGRATION.md`.
- Moved `files/REFACTOR_PLAN.md` -> `docs/archive/REFACTOR_PLAN.md`.
- Archived `files/get-intake-refactored.py` -> `scripts/archive/get-intake-refactored.py` (partially absorbed / unclear).
- Archived `files/provenance_tracker.py` -> `scripts/archive/provenance_tracker.py` (unreferenced).
- Removed empty `files/` directory.

### Phase D — security: `tidal_tokens.json`

- `.gitignore` already includes `tidal_tokens.json`; `git log -- tidal_tokens.json` returned no history.

### Phase E — structural issues (documented only)

E1. `tagslut/storage/migrations/0007*`
- Both `tagslut/storage/migrations/0007_isrc_primary_key.py` and the later-added ISRC uniqueness migration existed under `0007_*` prefixes at one point.
- `tagslut/storage/migration_runner.py` applies migrations sorted by full filename and records applied migrations by filename; the newer file was renamed to `tagslut/storage/migrations/0015_v3_isrc_partial_unique.py` to remove the shared prefix.

E2. `tagslut/metadata/models.py` vs `tagslut/metadata/models/`
- Both exist: `tagslut/metadata/models.py` and the package `tagslut/metadata/models/` (with `__init__.py`).
- Current imports in `tagslut/` and `tests/` use the package form (e.g. `from tagslut.metadata.models.types import ...`); no `from tagslut.metadata import models` import sites found.

E3. `tagslut/cli/scan.py` + `tagslut/cli/track_hub_cli.py` vs `tagslut/cli/commands/*`
- Both wrapper modules exist and re-export the canonical implementations from `tagslut/cli/commands/scan.py` and `tagslut/cli/commands/track_hub_cli.py`.
- `tagslut/cli/main.py` registers command groups from `tagslut/cli/commands/*` and does not import `tagslut/cli/scan.py` or `tagslut/cli/track_hub_cli.py` directly.
