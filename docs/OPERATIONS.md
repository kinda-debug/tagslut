# Operations


## CLI Reference and Common Operations


# tagslut Operations Manual

**Version:** 2.0.0
**Last Updated:** 2026-02-26

This is the single source of truth for operating the tagslut music library automation toolkit.

### Quick Start

```bash
# Activate environment
cd ~/Projects/tagslut
source .venv/bin/activate

# Verify CLI works
tagslut --help
```

### Database Setup

Set `TAGSLUT_DB` in `.env`.

```bash
TAGSLUT_DB=/Users/georgeskhawam/Projects/tagslut_db/EPOCH_2026-02-28/music_v2.db
```

WARNING: Never rely on doc defaults. Always set `TAGSLUT_DB` explicitly before running commands.

### Verify Migration

Use environment variables for the source/target DB paths, then run one verification command:

```bash
export V2_DB=/absolute/path/to/music_v2.db
export V3_DB=/absolute/path/to/music_v3.db
make verify-v3 V2="$V2_DB" V3="$V3_DB" STRICT=1
```

Treat this as the canonical preflight gate before destructive moves, epoch promotions, or enrichment passes.

### Identity QA Report

Generate an identity QA summary and CSV from your v3 DB:

```bash
make report-identity-qa V3="$V3_DB" OUT=output/identity_qa_v3.csv LIMIT=200
```

By default, inconsistency examples are scoped to active identities; add `--include-orphans` to include orphan rows in that section.

### Merge Duplicate Beatport Identities

Plan duplicate `beatport_id` merges (read-only):

```bash
make plan-merge-beatport-dupes V3="$V3_DB" OUT=output/merge_plan_beatport_v3.csv LIMIT=200
```

Execute merges (DB-only) after reviewing the plan:

```bash
make merge-beatport-dupes V3="$V3_DB" OUT=output/merge_plan_beatport_v3.csv EXECUTE=1
```

Then rerun identity QA and confirm duplicate Beatport groups are zero:

```bash
make report-identity-qa V3="$V3_DB" OUT=output/identity_qa_v3_post_merge.csv LIMIT=200
```

### Preferred Asset Selection

Plan preferred-asset selection (read-only):

```bash
make plan-preferred-asset V3="$V3_DB" OUT=output/preferred_asset_plan.csv LIMIT=500
```

Execute preferred-asset materialization:

```bash
make compute-preferred-asset V3="$V3_DB" OUT=output/preferred_asset_plan.csv VERSION=1 EXECUTE=1
```

Recommended cadence: run after identity merges, after major promotions/import batches, or weekly as a deterministic refresh.

### Identity Status Lifecycle (active / orphan / archived)

Statuses are materialized in `identity_status` and are computed for non-merged identities:
- `active`: has at least one linked asset
- `orphan`: no linked assets
- `archived`: explicitly parked identity (non-merged, excluded from normal workflows)
- `merged`: represented by `track_identity.merged_into_id IS NOT NULL` (not lifecycle-managed in `identity_status`)

Plan status recompute (read-only):

```bash
make plan-identity-status V3="$V3_DB" OUT=output/identity_status_plan.csv LIMIT=200
```

Compute/write statuses:

```bash
make compute-identity-status V3="$V3_DB" OUT=output/identity_status_plan.csv VERSION=1 EXECUTE=1
```

Optional conservative orphan archiving (refuses when timestamp fields are unavailable unless explicitly overridden):

```bash
make archive-orphans V3="$V3_DB" EXECUTE=1 THRESHOLD_DAYS=90
```

Downstream recommendation: default workflows and QA should filter to active identities (`identity_status.status='active'` and `track_identity.merged_into_id IS NULL`) unless explicitly auditing orphans.

### Canonical CLI Commands

All operations use these 7 command groups:

| Command | Purpose |
|---------|---------|
| `tagslut intake` | Download/intake orchestration |
| `tagslut index` | Library inventory & metadata |
| `tagslut decide` | Policy-based planning |
| `tagslut execute` | Execute plans |
| `tagslut verify` | Validate operations |
| `tagslut report` | Generate reports |
| `tagslut auth` | Provider authentication |

### Most Common Operations

### 0. Process Root (Phase-Controlled)

Use the canonical command:

```bash
tagslut intake process-root --db /path/to/music_v3.db --root /path/to/folder
```

Examples:

```bash
# Register only (discovery/asset registration)
tagslut intake process-root \
  --db /path/to/music_v3.db \
  --root /path/to/folder \
  --phases register

# Scan-only (register + integrity + hash; no identify/enrich/art/promote)
tagslut intake process-root \
  --db /path/to/music_v3.db \
  --root /path/to/folder \
  --scan-only

# Full pipeline (default behavior)
tagslut intake process-root \
  --db /path/to/music_v3.db \
  --root /path/to/folder \
  --providers beatport,deezer,apple_music,itunes
```

Promotion behavior for `process-root --phases promote` (or full pipeline):
- By default, promotion uses `preferred_asset` when available to choose one asset per identity deterministically.
- `--no-use-preferred-asset` disables preferred selection.
- `--require-preferred-asset` skips identities without a preferred asset under the current root.

Post-promote guardrail (expected: `OK` / `violation_count: 0`):

```bash
make check-promote-invariant V3="$V3_DB" ROOT="/path/to/promoted/root" MINUTES=240
```

### 1. Check Links Before Download

Check if tracks from Beatport/Tidal links already exist in your library:

```bash
# Create a file with URLs (one per line)
cat > ~/links.txt << 'EOF'
https://www.beatport.com/release/example/12345
https://tidal.com/browse/album/67890
EOF

# Run pre-download check
python tools/review/pre_download_check.py \
  --input ~/links.txt \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --out-dir output/precheck

### Clean Claude Export Files

```bash
tools/claude-clean /Users/georgeskhawam/Documents/StarredClaude.md \
  /Users/georgeskhawam/Documents/claude2.md \
  --out-dir output/claude_clean
```
```

**Outputs:**
- `precheck_decisions_<ts>.csv` - Per-track keep/skip with match method
- `precheck_summary_<ts>.csv` - Per-link statistics
- `precheck_keep_track_urls_<ts>.txt` - URLs for downloader (tracks NOT in library)

### 2. Download from Beatport

```bash
# Full sync (download missing + merge M3U)
tools/get-sync "https://www.beatport.com/release/example/12345"

# Report only (no download)
tools/get-report "https://www.beatport.com/release/example/12345"
```

**Note:** Beatport downloads work without interactive OAuth - uses stored config.

### 3. Download from Tidal

```bash
# Using router
tools/get "https://tidal.com/browse/album/67890"

# Or direct
tools/tiddl "https://tidal.com/browse/album/67890"
```

**Note:** Requires valid Tidal token. Check with `tagslut auth status`.

### 4. Download from Deezer

```bash
# Via router (auto FLAC + auto-register source=deezer)
tools/get "https://www.deezer.com/en/track/3451496391"

# Or direct wrapper
tools/deemix "https://www.deezer.com/en/track/3451496391"
```

**Defaults:** downloads to `~/Music/mdl/deezer`, bitrate `FLAC`, then runs `tagslut index register --source deezer --execute`.

### 5. Register New Files

```bash
tagslut index register \
  /path/to/new/files \
  --source bpdl \
  --execute
```

### 6. Check for Duplicates

```bash
tagslut index check \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### 7. Duration Check (DJ Safety)

```bash
# Quick check
tagslut index duration-check \
  /path/to/downloads \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db

# Full audit
tagslut index duration-audit \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### 7b. Sync Canonical Tags From Files (Lexicon-Friendly)

If Lexicon or another tagger updated file tags, sync BPM/Key/Genre/Energy/Danceability into the DB and emit an M3U of tracks still missing critical tags:

```bash
tools/metadata sync-tags \
  --read-files \
  --execute \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --path /Volumes/MUSIC/LIBRARY
```

### 7c. DJ Review App (Manual OK / Not OK)

```bash
tagslut dj review-app \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --library-prefix /Volumes/MUSIC/LIBRARY
```

See `docs/DJ_REVIEW_APP.md` for auto‑verdicts, filters, and USB export.

### 7d. DJ USB Health Check

```bash
python tools/dj_usb_analyzer.py \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --source /Volumes/MUSIC/DJ \
  --policy config/dj/dj_curation_usb_v8.yaml
```

### 8. Generate Execution Plan

```bash
# List available profiles
tagslut decide profiles

# Generate plan
tagslut decide plan \
  --policy library_balanced \
  --input output/candidates.json \
  --output output/move_plan.json
```

### 8. Execute Plan

#### Move execution (v3 safe mode)

```bash
tagslut ops run-move-plan plans/<file>.csv --strict
```

### 9. Verify Operations

```bash
# All verifications
tagslut verify duration --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify recovery --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
tagslut verify receipts --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### 10. Generate Reports

```bash
# M3U playlist
tagslut report m3u /Volumes/MUSIC/LIBRARY \
  --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db \
  --source library \
  --m3u-dir /Volumes/MUSIC/LIBRARY

# Duration report
tagslut report duration --db ~/Projects/tagslut_db/EPOCH_2026-02-10_RELINK/music.db
```

### What Each Command Writes

| Command | Writes To |
|---------|-----------|
| `tagslut index register` | `files` table in DB |
| `tagslut index check` | `duplicates` table in DB |
| `tagslut index duration-check` | Console output only |
| `tagslut index enrich` | `metadata_json` column in DB |
| `tagslut decide plan` | JSON file (--output) |
| `tagslut ops run-move-plan` | Preflight doctor + execute + postflight doctor + receipt JSON + archived plan CSV |
| `tagslut execute move-plan` | Moves files from plan CSV + updates DB path + JSONL log |
| `tagslut verify *` | Console output only |
| `tagslut report *` | Output files (M3U, CSV, MD) |
| `pre_download_check.py` | CSV + TXT files in --out-dir |

### Safe vs Unsafe Operations

### Safe (Read-Only)

- `tagslut index check`
- `tagslut index duration-check`
- `tagslut index duration-audit`
- `tagslut verify *`
- `tagslut report *`
- `tagslut auth status`
- `tagslut decide plan`
- `pre_download_check.py`
- `tools/get-report`

### Modifies Database Only

- `tagslut index register`
- `tagslut index enrich`
- `tagslut index set-duration-ref`

### Moves Files + Modifies Database

- `tagslut ops run-move-plan`
- `tagslut execute move-plan`
- `tagslut execute quarantine-plan`
- `tagslut execute promote-tags`
- `tools/review/promote_by_tags.py`
- `tools/review/move_from_plan.py`
- `tools/review/quarantine_from_plan.py`

### Downloads Files

- `tools/get` (unified router)
- `tools/get-sync` (Beatport)
- `tools/get-auto` (precheck + download missing)
- `tools/tiddl` (Tidal)
- `tools/deemix` (Deezer, auto-registers)

### DO NOT USE (Retired)

These commands were retired on Feb 9, 2026:

| Retired | Use Instead |
|---------|-------------|
| `tagslut scan` | `tagslut index ...` |
| `tagslut recommend` | `tagslut decide plan ...` |
| `tagslut apply` | `tagslut execute move-plan ...` |
| `tagslut promote` | `tagslut execute promote-tags ...` |
| `tagslut quarantine` | `tagslut execute quarantine-plan ...` |
| `tagslut mgmt` | `tagslut index ... + tagslut report m3u ...` |
| `tagslut metadata` | `tagslut auth ... + tagslut index enrich ...` |
| `tagslut recover` | `tagslut verify recovery ... + tagslut report recovery ...` |

**Note:** Use `tagslut` for all CLI commands.

### Downloader Locations

```
Beatport: tools/beatportdl/bpdl/bpdl (or ~/Projects/beatportdl/beatportdl-darwin-arm64)
Tidal:    tiddl (via PATH or tools/tiddl)
Deezer:   deemix (via PATH or tools/deemix)
```

## Environment Variables

Set in `.env` (full reference: `docs/OPERATIONS.md#configuration-and-environment`):

```
TAGSLUT_DB=/path/to/music.db
VOLUME_STAGING=/path/to/staging
VOLUME_ARCHIVE=/path/to/archive
VOLUME_SUSPECT=/path/to/suspect
VOLUME_QUARANTINE=/path/to/quarantine
TAGSLUT_ARTIFACTS=/path/to/artifacts
TAGSLUT_REPORTS=/path/to/artifacts/reports
```

## Config Quick Check

```bash
cd ~/Projects/tagslut
printenv TAGSLUT_DB
ls -l "$TAGSLUT_DB"
poetry run tagslut --help
```

See `docs/OPERATIONS.md#configuration-and-environment` for precedence rules and `zones.yaml` integration.

### Getting Help

```bash
# CLI help
tagslut --help
tagslut index --help
tagslut execute --help

# Policy docs
cat docs/OPERATIONS.md#script-surface-and-command-policy
cat docs/OPERATIONS.md#script-surface-and-command-policy
```

### Related Documentation

- `docs/WORKFLOWS.md` - Detailed workflow guides
- `docs/TROUBLESHOOTING.md` - Common issues and fixes
- `docs/ARCHITECTURE.md` - Recovery + provenance procedures
- `docs/archive/ZONES.md` - Zone system (archived)

### Source Registration Matrix

### Source Registration Matrix

| Source | Wrapper | --source Flag | Auto-register | Default Path |
|--------|---------|---------------|---------------|--------------|
| Beatport | `tools/get`, `tools/get-sync` | `bpdl` | No | config-defined |
| Tidal | `tools/get`, `tools/tiddl` | `tidal` | No | `~/Downloads/tiddl/` |
| Deezer | `tools/get`, `tools/deemix` | `deezer` | **Yes** | `~/Music/mdl/deezer` |
| Qobuz | N/A | N/A | N/A | **Not in active workflows** |

## Configuration and Environment


# Configuration Guide

This document defines how `tagslut` reads configuration from environment variables and optional config files.

### Scope

Configuration sources used by this project:

- `.env` in repo root (loaded by tooling that supports dotenv)
- Shell environment (`export KEY=value`)
- Optional zone config at `~/.config/tagslut/zones.yaml`
- CLI flags (highest priority for individual commands)

### Precedence

General precedence (highest to lowest):

1. CLI argument (`--db`, `--m3u-dir`, etc.)
2. Exported shell variable
3. `.env` value
4. `zones.yaml` auto-populated roots (for volume variables)
5. Command defaults

### Required Variables

`TAGSLUT_DB` is the only hard requirement for most inventory and reporting operations.

```bash
TAGSLUT_DB=/absolute/path/to/music.db
```

### Recommended Variables

Use these for stable, repeatable runs:

```bash
# Core paths
TAGSLUT_DB=/absolute/path/to/music.db
VOLUME_STAGING=/absolute/path/to/staging
VOLUME_ARCHIVE=/absolute/path/to/archive
VOLUME_SUSPECT=/absolute/path/to/suspect
VOLUME_QUARANTINE=/absolute/path/to/quarantine
TAGSLUT_ARTIFACTS=/absolute/path/to/artifacts
TAGSLUT_REPORTS=/absolute/path/to/artifacts/reports

# Scan behavior
SCAN_WORKERS=8
SCAN_PROGRESS_INTERVAL=100
SCAN_CHECK_INTEGRITY=true
SCAN_CHECK_HASH=true
SCAN_INCREMENTAL=true

# Decision tuning
AUTO_APPROVE_THRESHOLD=0.95
QUARANTINE_RETENTION_DAYS=30
PREFER_HIGH_BITRATE=true
PREFER_HIGH_SAMPLE_RATE=true
PREFER_VALID_INTEGRITY=true
```

### .env Bootstrap

Create `.env` from example:

```bash
cd /Users/georgeskhawam/Projects/tagslut
cp .env.example .env
```

Then edit values in `/Users/georgeskhawam/Projects/tagslut/.env`.

### zones.yaml Integration

`zones.yaml` is optional. When present, it can supply staging/archive/suspect/quarantine roots.

Example file:

`/Users/georgeskhawam/Projects/tagslut/config/zones.yaml.example`

Default user location expected by tooling:

`~/.config/tagslut/zones.yaml`

Minimal schema:

```yaml
zones:
  staging:
    - /path/to/staging
  archive:
    - /path/to/archive
  suspect:
    - /path/to/suspect
  quarantine:
    - /path/to/quarantine
```

### Validation Commands

Verify effective setup before heavy operations:

```bash
cd /Users/georgeskhawam/Projects/tagslut

# Confirm env values are visible
printenv TAGSLUT_DB
printenv VOLUME_STAGING

# Confirm DB path exists
ls -l "$TAGSLUT_DB"

# Confirm CLI is wired
poetry run tagslut --help

# Optional: show zone classification for one path
poetry run tagslut show-zone "$VOLUME_STAGING"
```

### Common Pitfalls

- `TAGSLUT_DB` points to an old epoch DB.
  Use the active DB explicitly via `--db` when needed.

- Relative paths in `.env`.
  Use absolute paths only.

- Missing mount points under `/Volumes`.
  Validate with `ls -ld /Volumes/...` before runs.

- Conflicting shell exports vs `.env`.
  `printenv` shows the winning values at runtime.

### Canonical References

- Environment template: `/Users/georgeskhawam/Projects/tagslut/.env.example`
- Operations guide: `/Users/georgeskhawam/Projects/tagslut/docs/OPERATIONS.md#cli-reference-and-common-operations`
- Zones details: `/Users/georgeskhawam/Projects/tagslut/docs/archive/ZONES.md`

## Script Surface and Command Policy


# Script Surface (Canonical vs Legacy)

This file is the authoritative map of where to run things in this repo.

Policy and deprecation rules are defined in:
- `docs/OPERATIONS.md#script-surface-and-command-policy`

### Canonical Entry Points

1. `poetry run tagslut intake ...`
Role: Download/intake orchestration and prefilter operations.

2. `poetry run tagslut index ...`
Role: Inventory registration, duplicate checks, duration checks, and metadata enrichment for indexed files.

3. `poetry run tagslut decide ...`
Role: Policy-profile listing and deterministic plan generation.

4. `poetry run tagslut execute ...`
Role: Execute move/quarantine/promote workflows from plans.

5. `poetry run tagslut verify ...`
Role: Validate duration/recovery/parity and move receipt consistency.

6. `poetry run tagslut report ...`
Role: M3U and operational reports (duration, recovery, plan summaries).

7. `poetry run tagslut auth ...`
Role: Provider authentication and token lifecycle flows.

8. `poetry run tagslut export usb ...`
Role: Export a source folder of MP3/FLAC tracks to a Pioneer CDJ-ready USB (writes PIONEER/ database via pyrekordbox, creates crate, outputs manifest).

### Rebrand Invocation

The preferred command brand is now `tagslut`.

Compatibility aliases:

### Operational Wrappers (Active)

These wrappers are active convenience entrypoints around canonical intake/report flows:

1. `tools/get <url>`
Role: Unified URL router.
- `tidal.com` -> `tools/tiddl`
- `beatport.com` -> `tools/get-sync`

2. `tools/get-sync <beatport-url>`
Role: Beatport sync mode (download missing + build merged M3U).

3. `tools/get-report <beatport-url>`
Role: Beatport report-only mode (no download).

4. `tools/tagslut [args...]`
Role: Local wrapper for `python -m tagslut`.

5. `tools/tag-build [options]`
Role: Build M3U from DB for library FLAC files missing ISRC.

6. `tools/tag-run --m3u <path> [options]`
Role: Run `onetagger-cli` on a symlink batch from M3U and emit summary artifacts.

7. `tools/tag [options]`
Role: Combined build + run OneTagger workflow with defaults.

### Transitional Wrapper Status

No transitional wrappers remain on the top-level `tagslut` CLI surface.

Retired in Phase 5:
- tagslut scan
- tagslut recommend
- tagslut apply
- tagslut promote
- tagslut quarantine ...
- tagslut mgmt ...
- tagslut metadata ...
- tagslut recover ...

Canonical groups now call internal hidden commands (`_mgmt`, `_metadata`, `_recover`)
to preserve implementation reuse without exposing transitional operator entrypoints.

Use `tagslut intake/index/decide/execute/verify/report/auth` for new work.

### Recovery Command Status

- `tagslut recovery` is currently a minimal stub logger and does not implement the full move pipeline described in some historical docs.
- For move execution today, use:
  - Plan generation scripts in `tools/review/`
  - `tools/review/move_from_plan.py`
  - `tools/review/quarantine_from_plan.py`
  - `tools/review/promote_by_tags.py` (`--move-log` for JSONL move audit output)
- Compatibility contract for these executors:
  - `docs/archive/MOVE_EXECUTOR_COMPAT.md`
  - `docs/archive/phase-specs-2026-02-09/` (phase runbooks and verification reports)

### Directory Ownership

- `tagslut/`: Productized CLI/package code.
- `tools/review/`: Active operational scripts.
- `legacy/tools/`: Archived historical scripts kept for reference and compatibility.
- `tools/review/promote_by_tags_versions/`: Historical snapshots.

### Rules for Keeping This Logical

1. New operational logic should go in `tagslut/` or `tools/review/`, not `legacy/`.
2. If a script is superseded, move it to an archive location and add a note in `legacy/tools/README.md`.
3. Keep docs aligned with real command help:
   - `poetry run tagslut --help`
   - `poetry run tagslut index --help`
   - `poetry run tagslut execute --help`
   - `poetry run tagslut auth --help`
4. Keep generated runtime outputs under `artifacts/` (`artifacts/logs`, `artifacts/tmp`, `artifacts/db`) instead of repo root.

# Surface Policy - tagslut (2026-02-09)

### Purpose

Define the supported command/script surface during v3 migration so operators and contributors use one logical path.

### Canonical Surface (Use For New Work)

1. `poetry run tagslut intake ...`
2. `poetry run tagslut index ...`
3. `poetry run tagslut decide ...`
4. `poetry run tagslut execute ...`
5. `poetry run tagslut verify ...`
6. `poetry run tagslut report ...`
7. `poetry run tagslut auth ...`
8. `poetry run tagslut export usb ...`

Reference map:
- `docs/OPERATIONS.md#script-surface-and-command-policy`

Branding note:
- `tagslut` is the preferred CLI brand.
- No legacy aliases are supported during migration.

### Transitional Surface

Transitional wrappers have been retired from top-level CLI exposure.

Retired in Phase 5:
1. `tagslut scan`
2. `tagslut recommend`
3. `tagslut apply`
4. `tagslut promote`
5. `tagslut quarantine ...`
6. `tagslut mgmt ...`
7. `tagslut metadata ...`
8. `tagslut recover ...`

### Removal Horizon

- Warning period starts: February 9, 2026
- Target archival/removal window: June-July 2026 (aligned to `docs/archive/REDESIGN_TRACKER.md` Phase 5)
- Dated decommission plan: `docs/archive/phase-specs-2026-02-09/PHASE5_LEGACY_DECOMMISSION.md`

### Phase 5 Decommission Gates

Compatibility wrappers were removed after satisfying these gates:

1. Coverage parity gate:
- Canonical replacement command is documented and tested.

2. Burn-in gate:
- No operator docs require the wrapper path as primary flow.
- Deprecation window has elapsed (minimum 30 days since warning start).

3. Safety gate:
- `scripts/check_cli_docs_consistency.py` passes.
- `scripts/audit_repo_layout.py` passes.
- Canonical `decide/execute/verify/report` regression tests pass.

### Enforcement Rules

1. Do not add new user-facing commands under `legacy/`.
2. Do not introduce new top-level CLI wrappers that bypass canonical surfaces.
3. Keep runtime artifacts out of repo root; write to `artifacts/`.
4. Keep docs synchronized with live CLI help and script surface map.

### Validation Hooks

1. `poetry run python scripts/audit_repo_layout.py`
2. `poetry run python scripts/check_cli_docs_consistency.py`
3. `poetry run tagslut --help`
4. `poetry run tagslut intake --help`
5. `poetry run tagslut index --help`
6. `poetry run tagslut decide --help`
7. `poetry run tagslut execute --help`
8. `poetry run tagslut verify --help`
9. `poetry run tagslut report --help`
10. `poetry run tagslut auth --help`
11. `poetry run tagslut --help` (compatibility alias)
12. Move executor contract doc: `docs/archive/MOVE_EXECUTOR_COMPAT.md`
13. V3 parity validator: `python scripts/validate_v3_dual_write_parity.py --db <db> --strict`
14. Policy profile lint: `python scripts/lint_policy_profiles.py`
15. Phase 3 executor tests: `pytest -q tests/test_exec_engine_phase3.py tests/test_exec_receipts_phase3.py`

CI integration:
- `.github/workflows/test.yml` runs `scripts/audit_repo_layout.py` on push/PR.

### Change Control

Any change to canonical or transitional surface must update all of:
- `docs/OPERATIONS.md#script-surface-and-command-policy`
- `docs/OPERATIONS.md#script-surface-and-command-policy`
- `docs/archive/MOVE_EXECUTOR_COMPAT.md` (if move execution contract changes)
- `docs/archive/phase-specs-2026-02-09/` (if phase runbook or decommission contract changes)
- `docs/archive/REDESIGN_TRACKER.md` (if milestone impact)

## Quality Gates



### Decision
- `mypy` is gating in CI, but enforced via a baseline to allow incremental cleanup.
- `lint` (flake8) is advisory for now and runs locally only.

### Mypy Baseline Workflow
- CI runs: `poetry run python scripts/mypy_baseline_check.py`
- Update baseline when intentional changes shift the error surface:
  `python scripts/mypy_baseline_check.py --update`

### Burn-Down Plan
- Target: reduce baseline error count by 20% per month.
- Rule: any touched module should not increase its error count; fix or add targeted ignores.
- Check-in cadence: update the baseline only when the net error count decreases.
