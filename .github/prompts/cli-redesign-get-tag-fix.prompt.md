# CLI Redesign: collapse to get / tag / fix / auth / admin

## Guardrails

- Do not recreate existing files.
- Do not modify `schema.py` without a migration.
- Do not redesign existing download, registration, enrichment, transcode, or storage internals beyond the minimum cohort/block-state persistence required by this prompt.
- This change is primarily command-surface, routing, and recovery-state plumbing. It is not a pipeline rewrite.

## Context

`tagslut` currently exposes wrapper-script entrypoints such as `ts-get`, `ts-enrich`, and `ts-auth`.

The approved redesign collapses the public CLI surface into five top-level Click command groups on the `tagslut` binary:

- `tagslut get` — acquisition from URL or local path
- `tagslut tag` — retroactive metadata and rehoard operations
- `tagslut fix` — resume blocked cohorts
- `tagslut auth` — token management
- `tagslut admin` — internal and advanced flows

The goal is to implement this new surface while preserving existing underlying pipeline behavior wherever possible.

---

## Failure and recovery model

Implement this before any CLI wiring.

### Per-file blocked state

If a file fails at any stage of a `get` pipeline, including download, register, enrich, transcode, or final output assembly:

- mark that file as blocked in `asset_file`:
  - `status='blocked'`
  - `blocked_reason='<stage>:<message>'`
- mark the corresponding `cohort_file` row:
  - `status='blocked'`
  - `blocked_stage='<stage>'`
  - `blocked_reason='<message or stage:message>'`

Do not abort the cohort on first failure. Continue attempting remaining files.

### Cohort blocked state

After all files in the cohort are attempted:

- if any file remains blocked, set the cohort row to:
  - `status='blocked'`
  - `blocked_reason` = a concise cohort-level summary
- print a full failure summary
- do not leave final output artifacts for that cohort

### Output artifact rule

This must be enforced strictly.

All cohort output artifacts must be written to a staging location first and promoted to final locations only if the entire cohort completes successfully.

Staged artifacts for a cohort live under `$STAGING_ROOT/<cohort_id>/` and are removed by deleting that directory tree on failure.

If the cohort ends blocked:

- do not write or retain final MP3 output for that cohort
- do not write or retain final M3U output for that cohort
- do not perform DJ admission for that cohort
- delete `$STAGING_ROOT/<cohort_id>/` and everything under it

No partial final artifacts may remain for a blocked cohort.

### Subsequent invocation reminder

Any later `tagslut` invocation that directly touches a blocked cohort must print a scoped reminder that names:

- the cohort ID
- the cohort source
- the recovery command to use

The reminder must be scoped, not global spam.

### Status visibility

`tagslut admin status` must list all blocked cohorts with enough detail to act on them:

- cohort ID
- source URL or source path summary
- cohort status
- cohort blocked reason
- blocked file count

---

## Migration 0018 — blocked cohort state

Create `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`:

```sql
ALTER TABLE asset_file ADD COLUMN status TEXT NOT NULL DEFAULT 'ok'
  CHECK (status IN ('pending','ok','blocked'));
ALTER TABLE asset_file ADD COLUMN blocked_reason TEXT;

CREATE TABLE IF NOT EXISTS cohort (
    id              INTEGER PRIMARY KEY,
    source_url      TEXT,
    source_kind     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','complete','blocked')),
    blocked_reason  TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT,
    flags           TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cohort_file (
    id              INTEGER PRIMARY KEY,
    cohort_id       INTEGER NOT NULL REFERENCES cohort(id),
    asset_file_id   INTEGER REFERENCES asset_file(id),
    source_path     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','ok','blocked')),
    blocked_reason  TEXT,
    blocked_stage   TEXT,
    created_at      TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
  VALUES ('v3', 18, '0018_blocked_cohort_state.sql');
```

Apply this migration as the first step. The Python migration wrapper pattern matches existing migrations in this directory.

---

## Command: `tagslut get <input>`

Accepts: provider URL, local file path, or local directory path.

Flags:
  --dj          Build MP3 output with DJ tags; write per-batch M3U in album
                folder and append to global dj_pool.m3u at MP3_LIBRARY root.
  --playlist    Emit M3U only (does not imply --dj).
  --fix         Re-resolve cohort, download missing/failed files, retag,
                clear blocked state on success. Not valid on local-root input
                (fail with a clear targeted error: `--fix is not valid on a
                local path. Use tagslut fix <cohort_id> or
                tagslut get <url> --fix to resume a remote cohort.`).

Dispatch logic:
  - URL → route to existing intake adapter (spotify, tidal, beatport, qobuz)
  - local path → register + tag (skip already-registered files silently)
  - local path + --fix → fail with targeted error above

Default flow (URL):
  resolve → download → register → enrich → [transcode+M3U if --dj]
  All steps run through the cohort/cohort_file tracking tables.

`--fix` on URL:
  Lookup existing cohort for URL in DB → re-enter pipeline at blocked_stage
  for each blocked cohort_file → clear blocked state on success → re-run
  output stage for whole cohort if fully resolved.

`--fix` and `tagslut fix` must produce identical DB state on success.

---

## Command: `tagslut tag [target]`

No target: retroactively retag/rehoard all eligible material.
Local path: retag that subset only.
URL: resolve URL back to existing cohort in DB; retag without downloading.

Flags:
  --dj      Retroactive DJ MP3 rebuild and reconcile for targeted cohort.
  --fix     Force fresh retag/rehoard pass; clears blocked state on success.
            No download — downloading is owned by `get`.

---

## Command: `tagslut fix [cohort_id]`

No argument: query DB for all cohorts with status='blocked'. Display list.
  Drive the resume pipeline for each in sequence.
With cohort_id: target a single blocked cohort by ID.

On full success: set cohort.status='complete', clear cohort_file blocked state.
On partial success: update remaining cohort_file rows only.

This command and `tagslut get <url> --fix` must converge on identical DB state.

---

## Command: `tagslut admin`

Move the following existing Click groups under `admin` as subgroups:
  intake, index, execute, verify, report, library, dj

Add:
  admin status   — list all blocked cohorts (ID, source, status, reason,
                   blocked file count)
  admin curate   — current staged `tagslut tag ...` batch-curation workflow

Keep compatibility aliases at the top level for one transition window.
Mark them deprecated in help text. They must dispatch to the admin equivalents.

---

## auth

No changes to internals. Route `tagslut auth` to existing auth command group.

---

## Help surface

`tagslut --help` must show only: get, tag, fix, auth, admin.
Deprecated aliases must NOT appear in the primary help.

---

## What to produce

1. `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`
2. `tagslut/cli/commands/get.py` — new Click command
3. `tagslut/cli/commands/tag.py` — new Click command (rename/refactor existing)
4. `tagslut/cli/commands/fix.py` — new Click command
5. `tagslut/cli/commands/admin.py` — wraps existing groups
6. Updated `tagslut/cli/main.py` — registers new groups, adds compat aliases
7. `tests/cli/test_get_dispatch.py` — dispatch routing tests
8. `tests/cli/test_fix_convergence.py` — fix/get --fix state convergence test
9. `tests/storage/v3/test_migration_0018.py`

Do not modify any existing pipeline logic, enrichment, or storage code outside of adding the cohort tracking calls to the intake path.

Commit after each file. One logical commit per file.
Run `poetry run pytest tests/cli/ tests/storage/v3/test_migration_0018.py -v` after completing all files.
