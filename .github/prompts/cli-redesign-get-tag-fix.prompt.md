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

* `--dj`
  * Build MP3 output with DJ tags
  * Write per-batch M3U in album folder
  * Append to global `dj_pool.m3u` at `MP3_LIBRARY` root
* `--playlist`
  * Emit M3U only
  * Does not imply `--dj`
* `--fix`
  * Re-resolve cohort, download missing or failed files, retag, and clear blocked state on success
  * Not valid on local-root input
  * Fail with this exact targeted error:

```text
--fix is not valid on a local path. Use tagslut fix <cohort_id> or tagslut get <url> --fix to resume a remote cohort.
```

### Dispatch logic

* URL → route to existing intake adapter (`spotify`, `tidal`, `beatport`, `qobuz`)
* local path → register + tag
* local path + `--fix` → fail with the targeted error above
* already-registered local files should be skipped silently

### Default flow for URL input

`resolve → download → register → enrich → [transcode + M3U if --dj]`

All steps run through the `cohort` / `cohort_file` tracking tables.

### `--fix` on URL

* look up the most recent blocked cohort for that exact URL in the DB
* re-enter the pipeline at `blocked_stage` for each blocked `cohort_file`
* clear blocked state on success
* re-run final output stage for the whole cohort if fully resolved

If no blocked cohort exists for that URL, fail clearly.

If multiple blocked cohorts exist for the same exact URL and recency does not unambiguously identify one target, fail clearly and instruct the operator to use `tagslut fix <cohort_id>`.

`tagslut get <url> --fix` and `tagslut fix` must produce identical DB state on success.

---

## Command: `tagslut tag [target]`

Accepted targets:

* local path
* URL resolving back to an existing cohort in the DB

Behavior:

* local path → retag that subset only
* URL → resolve URL back to existing cohort in DB and retag without downloading

No download is ever performed by `tag`.

### No target behavior

Do not silently operate on the full library.

If no target is provided and `--all` is not present, fail with a clear usage message.

Full-library retroactive retag/rehoard requires explicit `--all`.

### Flags

* `--dj`
  * Retroactive DJ MP3 rebuild and reconcile for the targeted cohort
* `--fix`
  * Force a fresh retag/rehoard pass
  * Clear blocked state on success only for cohorts blocked during post-download stages, such as:
    * register
    * enrich
    * retag
    * rehoard
    * transcode
    * playlist/output
  * No download: downloading is owned by `get`

If the cohort is blocked at download or earlier acquisition stages, fail with a targeted message directing the operator to `tagslut fix` or `tagslut get <url> --fix`.

---

## Command: `tagslut fix [cohort_id]`

No argument:

* query DB for all cohorts with `status='blocked'`
* display the list
* drive the resume pipeline for each in sequence

With `cohort_id`:

* target a single blocked cohort by ID
* fail clearly if the ID does not exist
* fail clearly if the cohort is not blocked

### Success behavior

On full success:

* set `cohort.status='complete'`
* clear cohort-level blocked state
* clear blocked state on `cohort_file` rows
* clear blocked state on corresponding `asset_file` rows
* run final output stage once for the whole cohort

On partial success:

* update only the rows that actually recovered
* leave unresolved blocked rows intact
* keep the cohort blocked with an updated summary

This command and `tagslut get <url> --fix` must converge on identical DB state.

---

## Command: `tagslut admin`

Move the following existing Click groups under `admin` as subgroups:

* `intake`
* `index`
* `execute`
* `verify`
* `report`
* `library`
* `dj`

Add:

* `admin status`
  * list all blocked cohorts with: ID, source, status, blocked reason, blocked file count
* `admin curate`
  * current staged `tagslut tag ...` batch-curation workflow

Keep compatibility aliases at the top level for one transition window.

Alias requirements:

* invokable at top level
* dispatch to the canonical `admin` equivalents
* marked deprecated on invocation
* hidden from primary help output

---

## auth

No changes to internals.

Route `tagslut auth` to the existing auth command group.

---

## Help surface

`tagslut --help` must show only: `get`, `tag`, `fix`, `auth`, `admin`.

Deprecated aliases must not appear in the primary help.

---

## What to produce

1. `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`
2. `tagslut/cli/commands/get.py` — new Click command
3. `tagslut/cli/commands/tag.py` — new Click command
4. `tagslut/cli/commands/fix.py` — new Click command
5. `tagslut/cli/commands/admin.py` — wraps existing groups
6. `tagslut/cli/main.py` — registers new groups, adds compat aliases
7. `tests/cli/test_get_dispatch.py` — dispatch routing tests
8. `tests/cli/test_fix_convergence.py` — `fix` / `get --fix` state convergence test
9. `tests/storage/v3/test_migration_0018.py`

Do not modify any existing pipeline logic, enrichment, or storage code outside of adding the cohort tracking calls to the intake path and the minimum recovery-state plumbing required by this prompt.

Commit after each file. One logical commit per file.

Run:

```bash
poetry run pytest tests/cli/ tests/storage/v3/test_migration_0018.py -v
```

After completion, report:

* files changed
* commit sequence
* test results
* any narrow deviations from spec
