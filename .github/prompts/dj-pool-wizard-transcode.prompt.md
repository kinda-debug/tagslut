# Prompt: DJ Pool Wizard Transcode Path Live Verification

## Context

Repo: `kinda-debug/tagslut`  
Branch: `dev`  
Canonical doc: `docs/DJ_POOL.md`, `docs/DJ_WORKFLOW.md` §DJ Pool Wizard,
`docs/REDESIGN_TRACKER.md` §4 open stream "Pool-wizard transcode path live
verification"

`tagslut dj pool-wizard` is the primary operator workflow for building a final
MP3 DJ pool from `MASTER_LIBRARY`. The relink-backed path (copy from existing
MP3 cache) is covered by live runs. The **transcode path** (FLAC → MP3 via
ffmpeg when no reusable MP3 source exists) has never been exercised against
real data.

## Problem Statement

The transcode execution path in `tagslut/exec/dj_pool_wizard.py` is untested
under real conditions. The open stream in REDESIGN_TRACKER.md notes it needs
a disposable fixture or copied dev-DB state that includes a row with an
`identity_id` and no reusable MP3 source to exercise the path.

Specific risks:

1. **`TranscodeError` raised but not caught** at the pool-wizard level —
   a single bad transcode kills the entire run instead of recording the failure
   and continuing.
2. **Post-transcode validation** (`existence`, `min_size`, `mutagen_readable`,
   `duration > 1s`) may not be wired to the pool-wizard's output artifact
   writer, so failures are silent.
3. **`--plan` flag leaks file writes** — `--plan` must be mutation-free; if
   the transcode path is reached during `--plan`, it must be skipped (or
   dry-run mocked) rather than executing.
4. **Artifact manifest** — the timestamped run directory must include a
   `transcode_failures.json` entry for any row where `TranscodeError` was
   raised, so operators can identify and re-queue failed tracks.

## Files To Read First

- `tagslut/exec/dj_pool_wizard.py`
- `tagslut/exec/mp3_build.py` — the transcode utility called by the wizard
- `tests/exec/test_dj_pool_wizard.py`
- `docs/DJ_POOL.md` — boundary and output/audit expectations

## Required Changes

1. Wrap the per-row transcode call in a `try/except TranscodeError` block.
   On failure: log the row to a `transcode_failures` list; do NOT raise; do
   NOT write an `mp3_asset` row for that identity.
2. After the run, write `transcode_failures.json` to the timestamped run
   directory (even if the list is empty, write `[]`).
3. Guard the transcode path behind the `--execute` flag. Under `--plan`,
   log the row as `would_transcode` in the plan artifact and skip.
4. Add a test fixture that creates an `asset_file` row pointing at a minimal
   valid FLAC (use `tests/fixtures/` or generate with `pydub`/`soundfile`),
   with no corresponding `mp3_asset` row, and asserts that `pool-wizard
   --execute` transcodes it, writes the `mp3_asset` row, and produces
   `transcode_failures.json` with `[]`.
5. Add a second fixture test: patch ffmpeg to return a non-zero exit code;
   assert the row appears in `transcode_failures.json` and no `mp3_asset`
   row is written.

## Verification

```bash
# plan run — must not write any files
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --non-interactive \
  --plan

ls /tmp/dj_pool_runs/  # must contain only plan artifact JSON, no MP3s

# execute run
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --non-interactive \
  --execute

ls /tmp/dj_pool_runs/<latest-run>/transcode_failures.json  # must exist
```

## Constraints

- Do NOT alter the `mp3_asset` or `dj_admission` schema.
- The transcode failure path must never raise to the caller — it is always
  caught, logged, and skipped.
- Run `poetry run mypy tagslut/exec/dj_pool_wizard.py --ignore-missing-imports`.
- Run `poetry run pytest tests/exec/test_dj_pool_wizard.py --tb=short -q`.
- Close the REDESIGN_TRACKER.md open stream "Pool-wizard transcode path live
  verification" by adding a **Completed** entry referencing this PR commit.

## Commit Message

```
fix(dj): pool-wizard transcode error handling, failure artifact, plan-mode guard
```
