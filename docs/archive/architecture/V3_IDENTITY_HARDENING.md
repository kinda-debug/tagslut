# V3 Identity Hardening

This document is the storage contract for completed v3 identity hardening work.

## Scope

Primary implementation files:

- `tagslut/storage/v3/schema.py`
- `tagslut/storage/v3/migration_runner.py`
- `tagslut/storage/v3/identity_service.py`
- `tagslut/storage/v3/merge_identities.py`
- `tagslut/storage/v3/dual_write.py`
- `tagslut/storage/v3/backfill_identity.py`
- `tagslut/storage/v3/migrations/0006_track_identity_phase1.py`
- `tagslut/storage/v3/migrations/0007_track_identity_phase1_rename.py`
- `tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py`
- `tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py`

Migration-runner policy:

- `tagslut/storage/v3/migration_runner.py` applies only numbered migration files
- underscore-prefixed modules in `tagslut/storage/v3/migrations/` are helper modules, not part of the default runner contract
- `_0009_chromaprint.py` is excluded from default migration discovery; `0009_chromaprint.py` is the numbered migration entrypoint

Primary test files:

- `tests/storage/v3/test_migration_0006.py`
- `tests/storage/v3/test_migration_0010.py`
- `tests/storage/v3/test_migration_0011.py`
- `tests/storage/v3/test_migration_runner_v3.py`
- `tests/storage/v3/test_transaction_boundaries.py`
- `tests/storage/v3/test_identity_service.py`
- `tests/storage/v3/test_backfill_v3_identity_links.py`
- `tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py`

## Table Contract

`tagslut/storage/v3/schema.py` defines `track_identity` with these identity-bearing columns:

- `isrc`
- `beatport_id`
- `tidal_id`
- `qobuz_id`
- `spotify_id`
- `apple_music_id`
- `deezer_id`
- `traxsource_id`
- `itunes_id`
- `musicbrainz_id`
- `artist_norm`
- `title_norm`
- `album_norm`
- `merged_into_id`

Hardening decisions in storage are active-row aware. A row is canonical and active when `merged_into_id IS NULL`. A merged loser remains in `track_identity` for lineage and provenance but must not block a canonical winner.

## Migration History

### `0006_track_identity_phase1.py`

Purpose:

- extends upgrade-path databases with canonical metadata fields
- adds `tidal_id`, `qobuz_id`, `deezer_id`, `traxsource_id`, `musicbrainz_id`, `itunes_id`
- adds `merged_into_id`
- adds lookup indexes, including `idx_track_identity_artist_title_norm`

Important limits:

- does not create uniqueness constraints
- does not normalize provider values
- does not enforce active-only semantics

### `0007_track_identity_phase1_rename.py`

Purpose:

- renames early phase-1 columns to canonical names on upgrade-path databases

Identity relevance:

- keeps the canonical field names stable for later merge-field copy behavior in `tagslut/storage/v3/merge_identities.py`

### `0010_track_identity_provider_uniqueness.py`

Purpose:

- first provider-uniqueness enforcement pass

Columns covered:

- `beatport_id`
- `tidal_id`
- `qobuz_id`
- `spotify_id`

Behavior:

- trims leading/trailing *spaces* with SQLite `TRIM(column)` (default trim set)
- converts values where `TRIM(column) = ''` to `NULL` (space-only becomes `NULL`; other whitespace characters are not treated as blank by default `TRIM()`)
- audits duplicates only across active rows with `merged_into_id IS NULL`
- groups duplicates by the stored column value (after the trimming/blank-to-`NULL` updates), with row inclusion gated by `TRIM(column) != ''`
- fails before index creation if duplicates remain
- creates active-only unique partial indexes:
  - `uq_track_identity_active_beatport_id`
  - `uq_track_identity_active_tidal_id`
  - `uq_track_identity_active_qobuz_id`
  - `uq_track_identity_active_spotify_id`

Storage rule established by `0010`:

- merged loser rows may retain duplicate provider values only until the merge code nulls the loser field or the row is otherwise excluded by `merged_into_id IS NOT NULL`

### `0011_track_identity_provider_uniqueness_hardening.py`

Purpose:

- second provider-uniqueness hardening pass

Columns covered:

- `apple_music_id`
- `deezer_id`
- `traxsource_id`

Behavior:

- trims leading/trailing spaces, tabs, carriage returns, and newlines with `TRIM(column, ' \t\n\r')`
- converts values where `TRIM(column, ' \t\n\r') = ''` to `NULL` (only this explicit set is treated as blank)
- audits duplicates only across active rows with `merged_into_id IS NULL`
- groups duplicates by the stored column value (after the trimming/blank-to-`NULL` updates), with row inclusion gated by `TRIM(column, ' \t\n\r') != ''`
- fails before index creation if duplicates remain
- creates active-only unique partial indexes:
  - `uq_track_identity_active_apple_music_id`
  - `uq_track_identity_active_deezer_id`
  - `uq_track_identity_active_traxsource_id`

Reason for the second pass:

- `0010` only hardened the first provider set
- Apple Music, Deezer, and Traxsource were still ordinary nullable text columns with non-unique secondary indexes
- tab-only and newline-only values were not normalized by default SQLite `TRIM()` behavior, so `0011` uses explicit trim characters for the second-pass fields

## Fresh-Schema Contract

`tagslut/storage/v3/schema.py` must create the same provider uniqueness guarantees that upgrade-path databases receive through migrations.

Current fresh-schema behavior:

- creates plain lookup indexes for all identity-bearing columns
- creates active-only unique partial indexes for:
  - `beatport_id`
  - `tidal_id`
  - `qobuz_id`
  - `spotify_id`
  - `apple_music_id`
  - `deezer_id`
  - `traxsource_id`
- records schema migration versions through `V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING = 11`

Fresh-schema note:

- `create_schema_v3()` inserts rows into `schema_migrations` for versions `1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11`
- `run_pending_v3()` uses the max recorded v3 version, so missing version `10` or `11` records in fresh-schema creation would cause incorrect reapplication attempts

## Provider Uniqueness Policy

Identifiers enforced in SQLite storage today:

- `beatport_id`
- `tidal_id`
- `qobuz_id`
- `spotify_id`
- `apple_music_id`
- `deezer_id`
- `traxsource_id`

Enforcement mode:

- unique only for active canonical rows
- not unique for merged loser rows
- blank values are allowed because the migrations normalize some blank forms to `NULL` and `NULL` does not participate in the partial unique index predicate:
  - `0010` providers: only space-only values normalize to `NULL` (SQLite `TRIM(x)` default)
  - `0011` providers: only values made blank by trimming the explicit set `' \t\n\r'` normalize to `NULL`

Identifiers not enforced as unique in SQLite storage:

- `isrc`
- `itunes_id`
- `musicbrainz_id`

Policy decision (current repo behavior):

- `itunes_id` and `musicbrainz_id` are helper-level identifiers only: `identity_service.py` uses them for lookup and identity-key derivation, but no migration or schema index enforces active-row uniqueness for them.

## Provider Repair Policy (Intentional Asymmetry)

This repository intentionally enforces provider uniqueness more broadly than it provides automated duplicate repair tooling.

Schema-level enforcement:

- active-row uniqueness is enforced for exactly seven provider ids: `beatport_id`, `tidal_id`, `qobuz_id`,
  `spotify_id`, `apple_music_id`, `deezer_id`, `traxsource_id`

Helper-level lookup/reuse:

- `identity_service.py` performs helper-level lookup/reuse by `isrc`, then by provider ids in `PROVIDER_COLUMNS`
- `PROVIDER_COLUMNS` is broader than schema uniqueness and includes `itunes_id` and `musicbrainz_id` in addition to
  the seven schema-enforced provider ids

Automated duplicate repair:

- duplicate discovery and merge automation are Beatport-only:
  - discovery: `find_duplicate_beatport_groups()`
  - merge: `merge_group_by_repointing_assets()` requires a nonblank `beatport_id` winner and rechecks active
    duplicate `beatport_id` after merge
- non-Beatport enforced-provider duplicate repair is operator-driven (no repository-provided generic merge tooling)

Reason these remain policy-only identifiers:

- `isrc` is used heavily for lookup, reuse, key derivation, and winner scoring, but duplicate `isrc` rows still exist as an operational conflict class; see `tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py`
- `itunes_id` exists in schema and payload extraction but has no active-only unique partial index and no migration that enforces uniqueness
- `musicbrainz_id` exists in schema and payload extraction but has no active-only unique partial index and no migration that enforces uniqueness

What “policy-only” means in this repository:

- the identifier can influence lookup, key derivation, conflict planning, or merge decisions in application code
- SQLite does not currently reject duplicate active rows for that identifier

## Identity Resolution Contract

`tagslut/storage/v3/identity_service.py` resolves or creates identities in this order:

1. exact `isrc`
2. exact provider id in `PROVIDER_COLUMNS`
3. fuzzy `(artist_norm, title_norm, duration)` reuse
4. create new identity

Important details:

- `derive_identity_key()` prefers `isrc`, then provider ids, then normalized text, then asset fallback
- `resolve_active_identity()` follows `merged_into_id` so callers can resolve losers to winners
- `resolve_active_identity()` detects `merged_into_id` cycles at runtime and raises `RuntimeError` if a cycle is encountered
- `_matched_identity_id_by_field()` prefers active rows first and then calls `resolve_active_identity()`

Storage consequence:

- provider uniqueness indexes protect exact provider-id reuse from producing multiple active rows
- `isrc` reuse is still application-policy behavior, not database-enforced uniqueness

## Merge Contract

`tagslut/storage/v3/merge_identities.py` is the canonical merge implementation for active duplicate groups.

Duplicate group discovery:

- only `beatport_id` duplicate groups are currently enumerated by `find_duplicate_beatport_groups()`

Winner selection:

- deterministic score in `choose_winner_identity()`
- scoring formula:
  - `enriched_at`: `+100`
  - `canonical_artist` and `canonical_title` both present: `+30`
  - `isrc` present: `+20`
  - active linked asset count: `+min(asset_count, 20)`
- tie-breaker: lowest `id`

Write behavior in `merge_group_by_repointing_assets()`:

- repoints `asset_link.identity_id` from losers to winner
- copies canonical fields from losers only when the winner field is blank
- sets `track_identity.merged_into_id` on loser rows
- nulls loser `beatport_id`
- syncs legacy `files.library_track_key`
- deletes loser `preferred_asset` rows
- rechecks for remaining active duplicate `beatport_id`
- asserts `asset_link` uniqueness
- asserts active links no longer point at merged identities

Provider-uniqueness interaction:

- the merge path actively nulls loser `beatport_id` after setting `merged_into_id`
- `0010` and `0011` allow merged losers to exist outside active uniqueness predicates, but merge code still clears the loser Beatport field to keep the active duplicate scan and post-merge state simple

## Transaction-Boundary Contract

The repository has explicit transaction ownership hardening for identity-write flows.

### `tagslut/storage/v3/dual_write.py`

`dual_write_registered_file()`:

- detects ownership with `owns_transaction = not conn.in_transaction`
- opens `BEGIN IMMEDIATE` only when it owns the transaction
- commits only when it owns the transaction
- rolls back only when it owns the transaction

Effect:

- standalone dual-write registration is atomic
- callers that already manage a transaction do not get nested transaction breakage or premature commits

### `tagslut/storage/v3/merge_identities.py`

`merge_group_by_repointing_assets()`:

- uses the same transaction-ownership pattern as dual write
- opens `BEGIN IMMEDIATE` only when not already inside a transaction
- commits only when it owns the transaction
- rolls back on any exception only when it owns the transaction

Effect:

- merge operations either fully apply or fully revert when called standalone
- validation failures after partial write steps do not leak half-applied merge state

### `tagslut/storage/v3/backfill_identity.py`

Backfill execution uses explicit batch transactions:

- starts with `BEGIN IMMEDIATE` when `--execute` is enabled
- commits every `commit_every` processed rows
- reopens `BEGIN IMMEDIATE` after each batch commit
- rolls back the active batch on per-row execution failure before continuing or aborting
- commits the final partial batch at the end

Effect:

- identity backfill is resilient to large runs
- batch boundaries are explicit and predictable
- immediate transactions remain compatible with identity resolution and asset linking writes

## Migration Runner Contract

`tagslut/storage/v3/migration_runner.py` rules:

- migration order comes from filename sort
- Python migration version comes from module `VERSION`
- migration execution skips any Python migration with `VERSION <= current max(schema_migrations.version where schema_name='v3')`
- SQL migrations are recorded by filename note
- `verify_v3_migration()` runs `PRAGMA foreign_key_check`, `PRAGMA integrity_check`, and `PRAGMA optimize`

Operator implication:

- schema version records in fresh-schema creation and migration files are part of the hardening contract
- duplicate-provider migrations fail before index creation, inside the migration transaction
