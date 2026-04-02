# V3 Identity Hardening Test Coverage

This document maps completed v3 identity hardening behavior to concrete tests.

## Migration Coverage

### `tests/storage/v3/test_migration_0006.py`

Covers:

- `0006_track_identity_phase1.py` adds canonical identity columns
- `merged_into_id` is added and remains nullable
- lookup indexes required by phase 1 are created
- migration is idempotent

Why it matters:

- later hardening code depends on the phase-1 columns existing on upgrade-path databases

### `tests/storage/v3/test_migration_0010.py`

Covers:

- duplicate active values fail `0010`
- merged loser rows do not block canonical winners for first-pass providers
- `NULL` values remain allowed under active-only unique partial indexes
- the migration runner applies `0010` cleanly and records the schema version

Provider fields covered:

- `beatport_id`
- `tidal_id`
- `qobuz_id`
- `spotify_id`

### `tests/storage/v3/test_migration_0011.py`

Covers:

- duplicate active values fail `0011` after normalization
- merged loser rows do not block canonical winners for second-pass providers
- `NULL`, blank, and values made blank by trimming the explicit set `' \t\n\r'` (space/tab/newline/CR) normalize to `NULL` and remain allowed
- the migration runner applies `0011` cleanly and records the schema version

Provider fields covered:

- `apple_music_id`
- `deezer_id`
- `traxsource_id`

## Migration Runner Coverage

### `tests/storage/v3/test_migration_runner_v3.py`

Covers:

- versioned migration application for v3 upgrade-path databases
- migration version ordering uses migration `VERSION`, not file count
- upgrade-path databases receive the expected schema additions

Identity-hardening relevance:

- protects against silent migration ordering errors that would skip or misapply versions `6`, `7`, `10`, or `11`

### `tests/storage/v3/test_migration_runner.py`

Covers:

- file-based migration application only once
- base-schema requirement enforcement before running pending migrations

Identity-hardening relevance:

- ensures migration execution fails fast when the v3 migration table is missing

## Transaction-Boundary Coverage

### `tests/storage/v3/test_transaction_boundaries.py`

`test_dual_write_registered_file_rolls_back_when_flow_fails`

Covers:

- `tagslut/storage/v3/dual_write.py:dual_write_registered_file()`
- a failure after asset upsert and identity/link writes causes full rollback when the function owns the transaction
- no partial `asset_file`, `track_identity`, or `asset_link` rows leak

`test_merge_group_by_repointing_assets_rolls_back_without_outer_transaction`

Covers:

- `tagslut/storage/v3/merge_identities.py:merge_group_by_repointing_assets()`
- a failure after partial merge writes causes full rollback when the function owns the transaction
- loser `beatport_id`
- loser `merged_into_id`
- winner canonical fields
- `asset_link`
- `preferred_asset`

Important scope limit:

- this is the Beatport merge path only; the repository has no provider-generic merge automation for the other
  schema-enforced provider ids (`tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`, `deezer_id`, `traxsource_id`)

This file is the authoritative proof that transaction ownership logic is part of identity hardening, not an incidental implementation detail.

## Identity Resolution Coverage

### `tests/storage/v3/test_identity_service.py`

Covers:

- exact reuse by `isrc`
- exact reuse by provider id
- fuzzy reuse by normalized artist/title plus duration tolerance
- active-identity resolution across one merge hop
- legacy mirror updates for `files` and `library_tracks`

Identity-hardening relevance:

- shows the repository still uses `isrc` as a strong lookup key without SQLite uniqueness enforcement
- confirms provider-id lookup behavior aligns with storage uniqueness expectations

Coverage gap:

- no test asserts `resolve_active_identity()` raises on a `merged_into_id` cycle

## Backfill Execution Coverage

### `tests/storage/v3/test_backfill_v3_identity_links.py`

Covers:

- twin FLAC/MP3 rows backfill into one identity
- resume-from-file-id behavior
- summary and checkpoint artifact generation
- execute mode still succeeds with immediate batch transactions

Identity-hardening relevance:

- verifies the backfill path can operate with explicit immediate transactions while creating/reusing identities and links
- proves batch transaction handling is part of the supported migration/backfill surface

## Conflict-Planning Coverage

### `tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py`

Covers:

- exact conflicts where multiple identities share one `isrc`
- fuzzy collisions where multiple identities are near matches for one file
- plan output to CSV and JSON with specific suggested manual actions

Identity-hardening relevance:

- this is the strongest repository evidence that `isrc` remains policy-only in storage
- duplicate `isrc` rows are expected to be surfaced as planned conflicts, not rejected by a SQLite unique constraint

## Coverage Matrix

Storage-enforced identifiers with migration coverage:

- `beatport_id`: `test_migration_0010.py`
- `tidal_id`: `test_migration_0010.py`
- `qobuz_id`: `test_migration_0010.py`
- `spotify_id`: `test_migration_0010.py`
- `apple_music_id`: `test_migration_0011.py`
- `deezer_id`: `test_migration_0011.py`
- `traxsource_id`: `test_migration_0011.py`

Policy-only identifiers with behavioral coverage:

- `isrc`: `test_identity_service.py`, `test_plan_backfill_identity_conflicts_v3.py`
- `itunes_id`: helper-level lookup participation only; no schema uniqueness enforcement and no direct tests proving reuse/duplicate handling
- `musicbrainz_id`: helper-level lookup participation only; no schema uniqueness enforcement and no direct tests proving reuse/duplicate handling

Transaction-boundary coverage:

- dual write rollback: `test_transaction_boundaries.py`
- merge rollback: `test_transaction_boundaries.py`
- backfill immediate transactions: `test_backfill_v3_identity_links.py`

## Required Verification Command

Targeted verification command for the v3 identity hardening surface:

```bash
pytest tests/storage/v3 -q
```

## Routine Proof Surface (Minimal)

Use the repository target that runs the smallest repeatable proof set for v3 identity integrity:

```bash
make check-v3-identity-integrity
```

Pytest tooling note:

- `pyproject.toml` disables the transitive `pylama` pytest plugin (`addopts = "-p no:pylama"`) so `poetry run pytest ...` is not blocked by pylama importing `pkg_resources`.

Use narrower commands only when iterating on one behavior:

```bash
pytest tests/storage/v3/test_migration_0010.py -q
pytest tests/storage/v3/test_migration_0011.py -q
pytest tests/storage/v3/test_transaction_boundaries.py -q
pytest tests/storage/v3/test_backfill_v3_identity_links.py -q
```
