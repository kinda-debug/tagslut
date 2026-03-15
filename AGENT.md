<!-- Status: Active document. Synced 2026-03-14. Historical or superseded material belongs in docs/archive/. -->

# AGENT.md - tagslut Repository Guide

## Role of this file

`AGENT.md` is the **vendor-neutral canonical instruction file** for all coding agents working in this repository — Claude, Copilot, Cursor, and any other automated tool. All agents must read this file first. Tool-specific overrides live in:

- `CLAUDE.md` + `.claude/CLAUDE.md` — Claude Code (CLI and GitHub Action)
- `.github/workflows/claude.yml` — how Claude is wired into GitHub Actions
- `.github/prompts/` — agent prompt customizations for specific workflows

When this file and a tool-specific override conflict, the tool-specific override wins for that tool only; all other agents follow this file.

## Purpose

`tagslut` manages a FLAC master library with deterministic identity tracking, auditable move execution, and derived DJ outputs.

The master FLAC library is always the source of truth. DJ pools, MP3 exports, playlists, and review artifacts are downstream products.

## Canonical Surface

Use these CLI groups for new work:

- `tagslut intake`
- `tagslut index`
- `tagslut decide`
- `tagslut execute`
- `tagslut verify`
- `tagslut report`
- `tagslut auth`

Specialized but still canonical:

- `tagslut mp3`
- `tagslut dj`
- `tagslut gig`
- `tagslut export`
- `tagslut init`

Policy-hidden commands such as `canonize`, `enrich-file`, `show-zone`, and `explain-keeper` are implementation details, not the primary operator surface.

## Active Operator Shortcuts

### Primary downloader

Use `tools/get <provider-url>` for normal intake.

- `tools/get --no-hoard` skips the tagging/enrich/art path.
- `tools/get --verbose` prints internal paths, artifacts, and batch snapshots.
- `tools/get --dj` is **deprecated** (fails immediately at runtime). Use the 4-stage DJ pipeline below for curated DJ library work.
- Beatport download flows are tokenless. Do not describe Beatport downloading as requiring tokens.

### DJ Pipeline (Canonical 4-Stage Workflow)

The 4-stage pipeline is the only recommended path for building a curated DJ library.

```
Stage 1: tagslut mp3 reconcile --db <DB> --mp3-root <DJ_ROOT> --execute
Stage 2: tagslut dj backfill   --db <DB>
Stage 3: tagslut dj validate   --db <DB>
Stage 4: tagslut dj xml emit   --db <DB> --out rekordbox.xml
         tagslut dj xml patch  --db <DB> --out rekordbox_v2.xml  (after changes)
```

Rules:
- `mp3_asset` rows are the source of truth for registered MP3 derivatives.
- `dj_admission` rows are the source of truth for what is in the DJ library.
- `dj_track_id_map` persists Rekordbox TrackIDs so cue points survive re-imports.
- `dj_export_state` stores a manifest hash of each emitted XML; `patch` verifies it.
- Never use `tools/get --dj` for scripted or repeatable DJ library maintenance.

### Root processing

Use `tagslut intake process-root` when you already have a staged root on disk.

For a v3 DB, the safe phase set is:

```bash
python -m tagslut intake process-root \
  --db <V3_DB> \
  --root <ROOT> \
  --library <MASTER_LIBRARY> \
  --phases identify,enrich,art,promote,dj
```

Important:

- `register`, `integrity`, and `hash` are legacy-scan phases and are blocked by the v3 guard when `--db` points at a v3 database.
- `--dry-run` currently applies to the `dj` phase only. Use `--phases dj --dry-run` to preview DJ FLAC tag enrichment and MP3 transcode without writing files.

### Plan execution

Use `tagslut execute move-plan` for plan CSV execution:

```bash
python -m tagslut execute move-plan \
  --plan plans/example.csv \
  --db <V3_DB> \
  --dry-run
```

Behavior:

- writes move receipts into `move_execution` and `provenance_event`
- keeps move intent in `move_plan`
- moves common per-track sidecars with the audio file when executing
- keeps collision policy as skip, never silent overwrite

Known sidecars:

- `.lrc`
- `.cover.jpg`, `.cover.jpeg`, `.cover.png`
- `.jpg`, `.jpeg`, `.png`

The legacy script `tools/review/move_from_plan.py` still exists for compatibility, but the canonical entry point is `tagslut execute move-plan`.

### DJ pool builder

The deterministic v3 DJ pool builder is `scripts/dj/build_pool_v3.py`, usually through the Make targets documented in `docs/OPERATIONS.md`.

The lightweight staged-root DJ phase also exists inside `tools/review/process_root.py`:

- enriches FLAC BPM/key/energy from v3 identity data when available
- falls back to Essentia for BPM/key/energy when needed
- can preview its work with `--phases dj --dry-run`

## Core Invariants

1. FLAC master library is canonical.
2. Identity truth lives in `track_identity`, not in file paths.
3. Every file move must be auditable.
4. Planning and execution stay separate: `decide -> execute -> verify`.
5. Runtime outputs belong under `artifacts/` or `output/`, not scattered across repo root.
6. Archive and historical docs must live under `docs/archive/`.
7. DJ workflows must not mutate the master library in ways that make it depend on DJ outputs.

## Import Layering (Enforced by Flake8)

This repository currently enforces the historical `tagslutcore -> tagslutdj` boundary using the live package paths `tagslut.core` and `tagslut.dj`.

- `tagslut.core*` can only depend on core/shared infrastructure such as `tagslut.core`, `tagslut.storage`, and `tagslut.db`-equivalent storage layers. It must not import `tagslut.dj*`.
- `tagslut.dj*` can depend on broader `tagslut.*` infrastructure, but it must not import `tagslut.core*` business logic.
- Violations fail flake8 via the import-rule plugin configured in [`.flake8`](/Users/georgeskhawam/Projects/tagslut/.flake8).

## Storage Model

Core v3 ownership:

- `asset_file`: physical file facts
- `track_identity`: canonical track facts
- `asset_link`: asset-to-identity binding
- `preferred_asset`: deterministic preferred asset per identity
- `identity_status`: active/orphan/archived lifecycle state
- `move_plan`, `move_execution`, `provenance_event`: move intent, outcome, and audit truth

If physical state and identity state disagree, trust the owner table for that fact category.

## Work Roots

Current operator work roots are split by intent:

- `FIX_ROOT`: salvageable metadata/tag issues
- `QUARANTINE_ROOT`: risky files needing manual review
- `DISCARD_ROOT`: deterministic duplicates such as `dest_exists`

These roots support operator workflow boundaries. They are not interchangeable with canonical library placement.

## Repository Layout

- `tagslut/`: runtime packages and CLI implementation
- `tools/`: active shell and Python wrappers
- `tools/review/`: legacy-compatible operational helpers and plan generators
- `scripts/`: focused maintenance, audits, migrations, and DJ helpers
- `config/`: policy/configuration inputs
- `docs/`: active documentation
- `docs/archive/`: historical or superseded documentation
- `legacy/`: retired code retained only for reference

## Phase 1 Stack Maintenance

For the current stacked Phase 1 branches, use:

```bash
tools/review/sync_phase1_prs.sh
```

It force-pushes the current migration, identity, and DJ-enrichment worktrees with `--force-with-lease` while keeping PR scope boundaries intact. See `README.md` and `docs/PHASE1_STATUS.md` for the current stack note.

## Quick Checks

Common validation commands:

⸻

DJ Pool Builder

Implementation:

scripts/dj/build_pool_v3.py

Execution model:

Default mode:

plan

Produces a manifest but does not copy files.

Execution mode:

--execute

Copies or transcodes assets into the pool.

Execution must always be explicit.

⸻

DJ MP3 Transcode and Sync

The --dj flag on tools/get triggers DJ MP3 transcoding after promotion.

Workflow:
	1.	tools/get <url> --dj transcodes promoted FLACs to DJ_ROOT.
	2.	A FLAC→MP3 map TSV is generated for post-move tag sync.
	3.	sync_dj_mp3_from_flac() refreshes DJ MP3 tags from enriched FLACs.

Tag policy:
	•	DJ MP3s keep: title, artist, album, date, genre, BPM, key, ISRC, label, energy, cover art.
	•	Lyrics (USLT, SYLT) are always stripped.
	•	ffmpeg encodes with -map_metadata -1 (strips all source metadata).

Implementation:

tagslut/exec/transcoder.py

Functions:
	•	transcode_to_mp3(): fresh FLAC-to-MP3 (prune_existing=True)
	•	sync_dj_mp3_from_flac(): refresh tags on existing DJ MP3 (prune_existing=False)

⸻

DJ Development Layers

DJ features are split into three layers.

Layer A — Documentation

docs/DJ_POOL.md
docs/DJ_WORKFLOW.md
docs/OPERATIONS.md

Layer B — DJ Curation Layer (B1)

tagslut/db/v3/dj_profile.py
scripts/dj/profile_v3.py
scripts/dj/export_ready_v3.py
tests/test_dj_profile_v3.py
tests/test_export_ready_v3.py

Layer C — DJ Pool Builder (B2)

scripts/dj/build_pool_v3.py
tests/test_build_pool_v3.py
Makefile DJ targets

Each layer should normally be delivered as separate PRs.

Documentation archive operations must never be mixed with code changes.

⸻

Git Hygiene Rules

Prefer explicit path staging.

git add <file>

Avoid staging the whole repository.

If interactive staging is required:

git add -p

Rules:
	•	stage only the intended hunks
	•	reject unrelated help-list changes
	•	reject archive doc churn

Always verify staged files:

git diff --cached --name-only


⸻

Branch Truth Gate

Do not begin remediation or feature work on an unproven branch.

Run before any focused PR:

git fetch origin
git log --oneline --decorate --graph --max-count=20 origin/dev..HEAD
git log --oneline --decorate --graph --max-count=20 HEAD..origin/dev
git diff --name-only origin/dev...HEAD
git diff --stat origin/dev...HEAD

Interpretation:
	•	empty diff both ways: branch is redundant; do not package a PR from it
	•	diff exists with a clean working tree: changes are committed and reviewable
	•	expected changes missing: use `git log --all -- <paths>` before doing more work

⸻

Worktree Recovery Procedure

If the working tree becomes contaminated:

git stash push -u -m "wip contaminated worktree"
git fetch origin
git reset --hard origin/dev
git clean -fd

Then restore only required files:

git restore --source=<stash> -- <paths>

Never restore an entire stash blindly.

⸻

Common Commands

Run tests:

poetry run python -m pytest -q
poetry run flake8 tagslut/ tests/
poetry run mypy tagslut/ --ignore-missing-imports

Review app regressions:

poetry run pytest -q tests/test_review_app.py

Primary downloader:

tools/get <provider-url>
tools/get <provider-url> --dj
tools/get <provider-url> --no-hoard
tools/get <provider-url> --verbose

Notes:
	•	`tools/get` is the primary user-facing downloader.
	•	`tools/get-intake` is the advanced/backend command for existing batch roots and `--m3u-only`.
	•	`tools/get-sync` is deprecated compatibility only.
	•	Default wrapper output should stay concise; use `--verbose` only when debugging wrapper behavior.
	•	`--force-download` should not replace an equal-or-better library file by default.

Tidal downloader (wrapper):

tools/tiddl <tidal-url>

Notes:
	•	Wraps system-installed TIDDL binary.
	•	Override binary path: TIDDL_BIN=/path/to/tiddl
	•	Resolves download root from ROOT_TD, TIDDL_DOWNLOAD_ROOT, or STAGING_ROOT.
	•	Syncs ~/.tiddl/config.toml download_path to match resolved root.

Work output zones:

FIX_ROOT         Salvageable metadata issues (FIX_ROOT or $VOLUME_WORK/fix)
QUARANTINE_ROOT  Risky files needing manual review (QUARANTINE_ROOT or $VOLUME_QUARANTINE)
DISCARD_ROOT     Deterministic duplicates (DISCARD_ROOT or $VOLUME_WORK/discard)

Quarantine lifecycle:

python tools/review/quarantine_gc.py --root <quarantine-root> --days <retention-days>
python tools/review/quarantine_gc.py --root <quarantine-root> --days <retention-days> --db <db> --execute

Notes:
	•	Default is dry-run. Pass --execute to delete.
	•	With --db, marks file_quarantine rows as deleted.
	•	JSON report written to artifacts/compare/quarantine_gc_<stamp>.json.

CI triage:

gh auth status
gh run list --limit 20 --json databaseId,workflowName,conclusion,headSha,url
gh run view <run-id> --json jobs,name,workflowName,conclusion,status,url
gh run view <run-id> --log

Performance triage:

poetry run python -m cProfile -o artifacts/pytest.prof -m pytest -q tests/test_review_app.py
sqlite3 <db-path> "EXPLAIN QUERY PLAN <sql>"

DJ candidate export:

V3=<path> OUT=output/dj_candidates.csv make dj-candidates

DJ ready export:

V3=<path> OUT=output/dj_ready.csv make dj-export-ready

Direct usage:

python scripts/dj/build_pool_v3.py --db <path> --out-dir <path>
python scripts/dj/build_pool_v3.py --db <path> --out-dir <path> --execute
python scripts/dj/build_pool_v3.py --db <path> --out-dir <path> --execute --fail-fast -v

DJ missing metadata queue:

V3=<path> OUT=output/dj_missing_metadata.csv make dj-missing-metadata

DJ profile update:

V3=<path> ID=<identity_id> RATING=4 ENERGY=3 make dj-profile-set

v3 safety checks:

V3=<path> make doctor-v3
V3=<path> ROOT=<promoted_root> make check-promote-invariant

Metadata helper workflows:

python tools/metadata_scripts/fetch_isrcs_musicbrainz.py --playlist <paths.m3u8> --user-agent "tagslut/1.0 (contact: <email>)" --out artifacts/isrc_fetch_report.csv
python tools/metadata_scripts/apply_isrcs_from_report.py --report artifacts/isrc_fetch_report.csv --execute
python tools/metadata_scripts/openkeyscan_apply_keys.py --playlist <paths.m3u8> --server-cmd "<openkeyscan command>" --out artifacts/openkeyscan_report.csv
python tools/metadata_scripts/apply_lexicon_csv_to_flac.py --csv <lexicon.csv> --root <flac_root> --out artifacts/lexicon_apply_report.csv
python tools/metadata_scripts/apply_lexicon_csv_to_mp3.py --csv <lexicon.csv> --root <mp3_root> --out artifacts/lexicon_apply_mp3_report.csv
python tools/metadata_scripts/sync_mp3_tags_from_flac.py --mp3-root <mp3_root> --flac-root <flac_root> --out artifacts/mp3_sync_from_flac_report.csv

MP3 sync defaults:

DJ_LIBRARY=<mp3_root>
MASTER_LIBRARY=<flac_root>

Current CI note:

Run `poetry run flake8 tagslut/ tests/` and `poetry run mypy tagslut/ --ignore-missing-imports`
before treating a `CI` failure as commit-specific.

⸻

Migration Verification Checklist

Before and after a v3 schema migration:

cp "$V3_DB" "${V3_DB}.pre_migration_$(date +%Y%m%d_%H%M%S).bak"
sqlite3 "$V3_DB" "PRAGMA foreign_keys = ON; PRAGMA foreign_key_check;"
sqlite3 "$V3_DB" "PRAGMA integrity_check;"

After adding columns or indexes:

sqlite3 "$V3_DB" "PRAGMA optimize;"

Required verification:
	•	use a connection that explicitly enables `foreign_keys`
	•	`foreign_key_check` must return no rows
	•	`integrity_check` must return `ok`
	•	run parity validation before treating the migration as complete

⸻

Operational Recovery

Backfill resume:

python scripts/backfill_v3_identity_links.py --db "$V3_DB" --execute
python scripts/backfill_v3_identity_links.py --db "$V3_DB" --execute --resume-from-file-id <file_id>

Rollback to pre-phase backup:

cp "${V3_DB}.pre_phase1_<stamp>.bak" "$V3_DB"
sqlite3 "$V3_DB" "PRAGMA integrity_check;"

Canonical-vs-legacy parity verification:

python scripts/validate_v3_dual_write_parity.py --db "$V3_DB" --strict
python scripts/db/verify_v3_migration.py --db "$V3_DB"

Merged-identity inspection:

python scripts/db/compute_identity_status_v3.py --db "$V3_DB" --out artifacts/identity_status.csv
sqlite3 "$V3_DB" "SELECT id, identity_key, merged_into_id FROM track_identity WHERE merged_into_id IS NOT NULL ORDER BY merged_into_id, id;"

Artifacts to inspect after backfill:
	•	`artifacts/backfill_v3_summary_<stamp>.json`
	•	`artifacts/backfill_v3_checkpoint_<stamp>_<file_id>.json`
	•	`artifacts/backfill_v3_abort_<stamp>.json`


⸻

Documentation Rules

When behavior changes, update:

docs/WORKFLOWS.md
docs/OPERATIONS.md
docs/SCRIPT_SURFACE.md
docs/SURFACE_POLICY.md
REPORT.md

Historical material must remain under:

docs/archive/

Bulk archive moves must be isolated in their own PR.

⸻

Forbidden Patterns

Do not:
	•	write to `track_identity` ad hoc outside the v3 identity service path
	•	chase `merged_into_id` outside the identity service
	•	perform per-file `library_track_sources` lookups in loops when a bulk preload is possible
	•	use filesystem discovery as the DJ candidate source once the Phase 1 gate is closed
	•	summarize or describe the contents of a file you have not opened

Required rule:
	•	the filesystem stores audio
	•	the database stores meaning

⸻

Operational Preferences

Long-running scripts should run in the foreground.

Do not run commands using:

&
nohup
detached sessions

Operators must be able to see command output.

Prefer verbose modes:

-v
-vv
--verbose


⸻

Post-Edit Validation

After changes run:

poetry run python -m pytest -q

Then repository audits:

poetry run python scripts/audit_repo_layout.py
