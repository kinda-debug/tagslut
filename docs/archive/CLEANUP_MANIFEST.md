# CLEANUP MANIFEST (2026-04-12)

## Deleted

- (none) — all Phase 1 “confirmed junk” targets were not present in this repo snapshot.

## Archived

- docs/archive/ROADMAP.md → docs/ROADMAP.md — restored roadmap to canonical location; added §7.4 pointing to this manifest.
- docs/archive/DJ_POOL.md → docs/DJ_POOL.md — restored DJ pool doc to canonical location.

- scripts/auto_env.py → scripts/archive/auto_env.py — unreferenced one-off `.env` materializer (not referenced by CI, package, or tests).
- scripts/backfill_v3_provenance_from_logs.py → scripts/archive/backfill_v3_provenance_from_logs.py — unreferenced one-off provenance backfill helper.
- scripts/capture_post_release_snapshot.py → scripts/archive/capture_post_release_snapshot.py — unreferenced post-release snapshot helper (writes under `artifacts/`).
- scripts/reconcile_track_overrides.py → scripts/archive/reconcile_track_overrides.py — unreferenced one-off maintenance script for `config/dj/track_overrides.csv`.

- tools/dj_review_app.py → tools/archive/dj_review_app.py — unreferenced launcher shim.
- tools/dj_usb_sync.py → tools/archive/dj_usb_sync.py — unreferenced legacy DJ USB sync / Rekordbox XML helper.
- tools/fix_blocklist.py → tools/archive/fix_blocklist.py — unreferenced one-off blocklist pruning helper.
- tools/claude-clean → tools/archive/claude-clean — unreferenced convenience wrapper (calls `tools/review/claude_clean.py`).
- tools/get-all → tools/archive/get-all — unreferenced legacy end-to-end pipeline orchestrator.
- tools/get-auto → tools/archive/get-auto — unreferenced legacy precheck+download helper.
- tools/get-sync → tools/archive/get-sync — deprecated compatibility alias; unreferenced.

## Left in place (uncertain)

- tools/dj_usb_analyzer.py — compatibility shim name collides with existing `tools/archive/dj_usb_analyzer.py`; left in place to avoid ambiguity.
- artifacts/**/*.log — log files remain under `artifacts/` (including `artifacts/intake/logs/` and `artifacts/logs/`). Policy requires moving them to `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/`, but this pass did not move them.

## Not touched (active)

- No changes under `tagslut/`, `tests/`, `config/`, `supabase/`, `.github/workflows/`, `pyproject.toml`, `poetry.lock`.
- No changes to `tools/get`, `tools/get-intake`, or anything under `tools/review/`.

## 2026-04-12 — Supplement cleanup pass (audit 2026-03-29)

### Phase A — Root junk (deletion list)

Not found at repo root (no action taken):
- `qqqq.txt`
- `sdf.dc`
- `claudebs.md`
- `tagslut_DIRECTIVES_REVISED_2026-03-26.md`
- `DJ_PIPELINE_FULL_REPAIR_CODEX.md`
- `POSTMAN_AI_PROMPT.md`
- `postman-fix-prompt.md`
- `20260317_rekordbox.xml`

### Phase B — Duplicate root `process_dedupe.py`

- `process_dedupe.py` not present at repo root; only `scripts/process_dedupe.py` exists.

### Phase C — `files/` directory

- `files/` not present (no action taken).

### Phase D — Security: `tidal_tokens.json`

- `.gitignore` already contains `tidal_tokens.json`.
- `git log --all --full-history -- tidal_tokens.json` returned no history.

### Phase E — Structural bugs (investigation only; do not fix)

#### E1. Migration `0007` collision (`tagslut/storage/migrations/0007*`)

- Only `tagslut/storage/migrations/0007_isrc_primary_key.py` exists.
- `tagslut/storage/migration_runner.py` applies migrations in lexicographic filename order and tracks applied state by full filename in `migrations_applied.name`.

#### E2. `metadata/models.py` vs `metadata/models/` package

- Both exist: `tagslut/metadata/models.py` and `tagslut/metadata/models/` (package).
- `import tagslut.metadata.models` resolves to `tagslut/metadata/models/__init__.py` (the package); `tagslut/metadata/models.py` is shadowed for that import name.
- No `from tagslut.metadata import models` import sites found under `tagslut/` or `tests/` (2026-04-12).
- Import sites using `from tagslut.metadata.models...` (2026-04-12):
  - `tagslut/cli/commands/_enrich_helpers.py`
  - `tagslut/exec/prescan_tag_completion.py`
  - `tagslut/metadata/__init__.py`
  - `tagslut/metadata/enricher.py`
  - `tagslut/metadata/models.py`
  - `tagslut/metadata/models/__init__.py`
  - `tagslut/metadata/pipeline/runner.py`
  - `tagslut/metadata/pipeline/stages.py`
  - `tagslut/metadata/providers/base.py`
  - `tagslut/metadata/providers/beatport.py`
  - `tagslut/metadata/providers/qobuz.py`
  - `tagslut/metadata/providers/reccobeats.py`
  - `tagslut/metadata/providers/tidal.py`
  - `tagslut/metadata/source_selection.py`
  - `tagslut/metadata/store/db_reader.py`
  - `tagslut/metadata/store/db_writer.py`
  - `tests/core/test_metadata_smoke.py`
  - `tests/exec/test_prescan_tag_completion.py`
  - `tests/metadata/providers/test_qobuz_provider.py`
  - `tests/metadata/test_beatport_provider_api.py`
  - `tests/metadata/test_enrichment_stats.py`
  - `tests/metadata/test_metadata_models.py`
  - `tests/metadata/test_metadata_router.py`
  - `tests/metadata/test_pipeline_runner.py`
  - `tests/metadata/test_pipeline_stages.py`
  - `tests/metadata/test_reccobeats_provider.py`
  - `tests/metadata/test_source_selection.py`
  - `tests/test_db_writer.py`
  - `tests/test_enrichment_cascade.py`
  - `tests/test_tidal_beatport_enrichment.py`

#### E3. `cli/scan.py` + `cli/track_hub_cli.py` vs `cli/commands/` duplicates

- Command implementations exist under `tagslut/cli/commands/`:
  - `tagslut/cli/commands/scan.py`
  - `tagslut/cli/commands/track_hub_cli.py`
- Compatibility wrappers exist at:
  - `tagslut/cli/scan.py` (re-exports from `tagslut.cli.commands.scan`)
  - `tagslut/cli/track_hub_cli.py` (imports `main` / re-exports from `tagslut.cli.commands.track_hub_cli`)
- `tagslut/cli/main.py` and `tagslut/__main__.py` do not import these modules; they appear intended for `python -m tagslut.cli.scan` / `python -m tagslut.cli.track_hub_cli` compatibility.
