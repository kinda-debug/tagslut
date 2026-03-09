<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

## Phase 1 Invariants (Active)

- All writes to track_identity must go through tagslut/storage/v3/identity_service.py
- No module outside tagslut/storage/v3/ may reference merged_into_id
- Legacy mirrors (files, library_tracks) must be updated on every identity write via mirror_identity_to_legacy()
- Fuzzy matches must not overwrite exact-provider fields unless the target field is empty
- Schema PRs must not contain service logic or backfill logic
- SQLite migrations must enable FK per connection and run foreign_key_check + integrity_check
- DJ candidate paths must read from v3 tables only, no filesystem heuristics
- No direct writes to files.canonical_* or files.library_track_key outside the mirror service

Branding and alias policy:
- `tagslut` is the preferred command brand.
- `dedupe` is a deprecated compatibility alias and is scheduled for removal on **2026-06-01**.

Retired wrappers for new work:
- `scan`, `recommend`, `apply`, `promote`, `quarantine`, `mgmt`, `metadata`, `recover`

## Core Invariants
1. Master FLAC library is the source of truth.
2. DJ MP3 pools are derived outputs, not source data.
3. Move workflows are move-only and auditable (receipts/logs).
4. Integrity and duration gates must be respected before promotion.
5. Prefer deterministic planning/execution (`decide` -> `execute` -> `verify`).
6. Keep runtime outputs in `artifacts/`, not repository root.
7. **NO PERMANENT REMOVAL**: never permanently delete files or folders, even if asked; only move items to Trash.

## DJ Workflow (v3)
Operator-level DJ path (downstream only):
1. Candidates export (read-only) from v3 identities.
2. DJ profile curation (B1) in `dj_track_profile`, then DJ-ready export if present.
3. DJ pool builder (B2) with plan-first defaults; execute must be explicit.

Policy defaults:
- Preferred-asset principle: DJ pool and promotion must use preferred assets when available.
- Identity status: exclude orphans by default unless the operator opts in.

## DJ Pool Builder (B2) — Branch/PR Hygiene
- PRs must be minimal scope and limited to the intended layer (docs, B1, or B2).
- Never mix docs archive churn with DJ code or DJ docs.
- If the worktree gets contaminated:
  - `git stash push -u -m "wip: contaminated worktree"`
  - `git fetch origin && git reset --hard origin/dev && git clean -fd`
  - Restore only required paths from the stash using `git restore --source=<stash> -- <paths>`
- For PR splitting, stage exact paths (non-interactive preferred). If using `git add -p Makefile`, stage only the targeted block and reject help-list churn.

## Commands
Prefer Make targets if present; otherwise call the scripts directly.

- Run tests:
  - `poetry run python -m pytest -q`
- DJ pool plan:
  - `V3_DB=<path> POOL_OUT=<path> make dj-pool-plan`
  - `python scripts/dj/build_pool_v3.py --db <path> --out-dir <path>`
- DJ pool execute (explicit):
  - `V3_DB=<path> POOL_OUT=<path> make dj-pool-run EXECUTE=1`
  - `python scripts/dj/build_pool_v3.py --db <path> --out-dir <path> --execute`

## Repository Ownership Map
- `tagslut/`: productized package and CLI code
- `tools/review/`: active operational scripts
- `scripts/`: maintenance, audits, migrations, batch helpers
- `config/`: policies, blocklists, workflow configs
- `docs/`: active operator/developer docs
- `docs/archive/`: historical docs only (do not treat as active policy)
- `legacy/`: retired code and historical assets only
- `artifacts/`, `output/`: generated runtime outputs

## Agent Workflow Expectations
Before editing:
1. Read the active docs relevant to the target area (at minimum from `docs/`).
2. Read the source files that implement the behavior being changed.
3. Confirm command/help behavior directly when changing CLI surface.

During edits:
1. Prefer `tagslut/` and `tools/review/` for active logic.
2. Do not introduce new operator-facing behavior under `legacy/`.
3. Keep DB/schema changes additive and migration-safe.
4. Preserve auditable behavior for file moves and promotions.

## Operator Interaction Preferences
1. Do not run long scripts in the background (`&`, `nohup`, detached sessions, or similar).
2. Keep long-running commands in the foreground so output is visible while they run.
3. Keep the operator in the loop before running heavyweight commands.
4. Use verbose mode by default for scripts/commands when supported (`--verbose`, `-v`, `-vv`).
5. Avoid silent execution patterns unless explicitly requested.
6. If the operator asks to remove/delete something, send it to Trash instead of permanently deleting it.

After edits (minimum validation set):
1. `poetry run pytest -q`
2. `poetry run python scripts/audit_repo_layout.py`
3. `poetry run python scripts/check_cli_docs_consistency.py`
4. If CLI changed: run relevant `tagslut <group> --help` checks

## Documentation Update Rules
When behavior or command surface changes, update the matching docs in the same change set:
- `docs/WORKFLOWS.md`
- `docs/OPERATIONS.md`
- `docs/SCRIPT_SURFACE.md`
- `docs/SURFACE_POLICY.md`
- `REPORT.md` (if strategy/positioning changes)

If a change only affects historical docs, keep it under `docs/archive/` and do not re-promote archived workflows into active docs.

## Practical Safety Notes
- Pre-download check should be the default posture before downloads.
- Provider defaults in active workflows are typically Beatport/Tidal unless explicitly overridden.
- Treat `warn`/`fail` duration buckets as review queues, not auto-delete signals.
- Rekordbox/Lexicon are downstream consumers; they are not authoritative source-of-truth stores.
