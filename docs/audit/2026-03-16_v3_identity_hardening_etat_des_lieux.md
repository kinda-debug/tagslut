# 2026-03-16 v3 identity hardening etat des lieux

Scope: proof-only on three questions.

## 1. Fresh schema vs upgrade-path equivalence

### Proven

Fresh bootstrap via [`create_schema_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py) and a supported `v9 -> v11` upgrade path produce the same effective schema for:

- [`track_identity`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
- [`asset_file`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
- [`asset_link`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
- [`preferred_asset`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
- all seven active-provider unique partial indexes
- all relevant non-unique lookup indexes on those tables

Proof method:

- Fresh DB: `create_schema_v3()` on `/tmp/tagslut_audit/fresh_v11.sqlite`
- Upgrade DB: `create_schema_v3()`, then remove versions `10` and `11` plus the seven `uq_track_identity_active_*` indexes, then run [`run_pending_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py) against a filtered migrations dir containing only:
  - [`0010_track_identity_provider_uniqueness.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py)
  - [`0011_track_identity_provider_uniqueness_hardening.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py)

Filtered runner output:

```text
['0010_track_identity_provider_uniqueness.py', '0011_track_identity_provider_uniqueness_hardening.py']
```

Exact `sqlite_master` evidence:

- [`asset_file`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py): identical `CREATE TABLE` SQL in both DBs, including `duration_measured_ms`, `chromaprint_fingerprint`, `chromaprint_duration_s`, and `path TEXT NOT NULL UNIQUE`.
- [`track_identity`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py): identical `CREATE TABLE` SQL in both DBs, including `apple_music_id`, `deezer_id`, `traxsource_id`, `itunes_id`, `musicbrainz_id`, and `merged_into_id INTEGER REFERENCES track_identity(id)`.
- [`asset_link`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py): identical `CREATE TABLE` SQL in both DBs, including `UNIQUE(asset_id)` and `active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))`.
- [`preferred_asset`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py): identical `CREATE TABLE` SQL in both DBs.

Provider unique index definitions from `sqlite_master`:

```text
fresh uq_track_identity_active_spotify_id:
CREATE UNIQUE INDEX uq_track_identity_active_spotify_id
            ON track_identity(spotify_id)
            WHERE spotify_id IS NOT NULL
              AND TRIM(spotify_id) != ''
              AND merged_into_id IS NULL

upgrade uq_track_identity_active_spotify_id:
CREATE UNIQUE INDEX uq_track_identity_active_spotify_id
        ON track_identity(spotify_id)
        WHERE spotify_id IS NOT NULL
          AND TRIM(spotify_id) != ''
          AND merged_into_id IS NULL
```

Same for:

- `uq_track_identity_active_beatport_id`
- `uq_track_identity_active_tidal_id`
- `uq_track_identity_active_qobuz_id`
- `uq_track_identity_active_spotify_id`
- `uq_track_identity_active_apple_music_id`
- `uq_track_identity_active_deezer_id`
- `uq_track_identity_active_traxsource_id`

`PRAGMA index_list(track_identity)` proof:

- Fresh and upgrade DBs both contain the same 20 entries:
  - `idx_track_identity_key`
  - `idx_track_identity_isrc`
  - `idx_track_identity_beatport`
  - `idx_track_identity_tidal`
  - `idx_track_identity_qobuz`
  - `idx_track_identity_spotify`
  - `idx_track_identity_apple_music`
  - `idx_track_identity_deezer`
  - `idx_track_identity_traxsource`
  - `idx_track_identity_itunes`
  - `idx_track_identity_musicbrainz`
  - `idx_track_identity_merged_into`
  - the seven `uq_track_identity_active_*` partial unique indexes
  - `sqlite_autoindex_track_identity_1`

`PRAGMA index_xinfo(...)` proof:

- Fresh and upgrade DBs match for all seven provider-unique indexes.
- Example:

```text
PRAGMA index_xinfo(uq_track_identity_active_apple_music_id)
(0, 7, 'apple_music_id', 0, 'BINARY', 1)
(1, -1, None, 0, 'BINARY', 0)
```

The same single indexed column layout holds for all seven provider-unique indexes in both DBs.

### Not equivalent

`schema_migrations` contents are not equivalent.

Fresh bootstrap records:

```text
10|active provider-id unique partial indexes
11|active provider-id unique partial indexes hardening pass
```

Upgrade path records:

```text
10|0010_track_identity_provider_uniqueness.py
11|0011_track_identity_provider_uniqueness_hardening.py
```

Reason:

- [`create_schema_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py) inserts descriptive notes.
- [`run_pending_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py#L124) overwrites notes with migration filenames via `_record_applied_version(..., note=migration_path.name)`.

### Missing proof / current blocker

The default migration runner is not currently usable as a proof path from `v9` to `v11` with the repo’s default migrations directory.

Observed command output:

```text
RuntimeError: V3 migration filename must start with a numeric version: _0009_chromaprint.py
```

Cause:

- [`run_pending_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py#L124) iterates every `.py` migration file.
- [`_version_from_filename()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py) rejects [`_0009_chromaprint.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/_0009_chromaprint.py) before version skipping happens.

So:

- Proven: effective schema equivalence for a filtered, supported `v9 -> v11` path.
- Not proven: full default-directory upgrade-path equivalence, because the default runner currently errors first.

## 2. Provider-duplicate repair asymmetry

Matrix:

| field | schema enforcement | helper-level reuse logic | duplicate discovery helper | merge automation | tests |
|---|---|---|---|---|---|
| `isrc` | No | Yes | No dedicated helper | No | Yes |
| `beatport_id` | Yes | Yes | Yes | Yes | Yes |
| `tidal_id` | Yes | Yes | Via migration audit only | No | Yes |
| `qobuz_id` | Yes | Yes | Via migration audit only | No | Yes |
| `spotify_id` | Yes | Yes | Via migration audit only | No | Yes |
| `apple_music_id` | Yes | Yes | Via migration audit only | No | Yes |
| `deezer_id` | Yes | Yes | Via migration audit only | No | Yes |
| `traxsource_id` | Yes | Yes | Via migration audit only | No | Yes |
| `itunes_id` | No | Yes | No | No | No direct proof |
| `musicbrainz_id` | No | Yes | No | No | No direct proof |

### Proof per column class

Schema enforcement:

- Present in fresh schema for:
  - [`uq_track_identity_active_beatport_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_tidal_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_qobuz_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_spotify_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_apple_music_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_deezer_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
  - [`uq_track_identity_active_traxsource_id`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py)
- Absent for `isrc`, `itunes_id`, `musicbrainz_id` in [`schema.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/schema.py) and in migrations [`0010`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py) / [`0011`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py).

Helper-level reuse logic:

- [`identity_service.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/identity_service.py) `PROVIDER_COLUMNS` includes:
  - `beatport_id`
  - `tidal_id`
  - `qobuz_id`
  - `spotify_id`
  - `apple_music_id`
  - `deezer_id`
  - `traxsource_id`
  - `itunes_id`
  - `musicbrainz_id`
- `isrc` is checked separately before provider IDs in [`resolve_or_create_identity()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/identity_service.py).

Duplicate discovery helpers:

- Beatport only:
  - [`find_duplicate_beatport_groups()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/merge_identities.py)
- Migration-audit-only discovery exists for:
  - `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id` in [`0010_track_identity_provider_uniqueness.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py)
  - `apple_music_id`, `deezer_id`, `traxsource_id` in [`0011_track_identity_provider_uniqueness_hardening.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py)
- No dedicated duplicate-discovery helper found for:
  - `isrc`
  - `itunes_id`
  - `musicbrainz_id`

Merge automation:

- Beatport only:
  - [`merge_group_by_repointing_assets()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/merge_identities.py) requires a winner with non-empty `beatport_id`, nulls loser `beatport_id`, and rechecks duplicate active `beatport_id`.
- No generic provider merge automation found for any other provider field.

Tests:

- `isrc`:
  - exact reuse: [`test_identity_service.py`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_identity_service.py)
  - duplicate conflict planning: [`test_plan_backfill_identity_conflicts_v3.py`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py)
- `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`:
  - migration coverage: [`test_migration_0010.py`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_migration_0010.py)
  - direct beatport helper reuse proof: [`test_identity_service.py`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_identity_service.py)
- `apple_music_id`, `deezer_id`, `traxsource_id`:
  - migration coverage: [`test_migration_0011.py`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_migration_0011.py)
- No direct test found for helper-level reuse on:
  - `tidal_id`
  - `qobuz_id`
  - `spotify_id`
  - `apple_music_id`
  - `deezer_id`
  - `traxsource_id`
  - `itunes_id`
  - `musicbrainz_id`
- No merge-automation test found for non-Beatport provider duplicates because no such automation exists.

## 3. Transaction ownership proof

Code under test:

- [`dual_write_registered_file()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/dual_write.py#L560)
- [`resolve_or_create_identity()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/identity_service.py#L579)
- [`merge_group_by_repointing_assets()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/merge_identities.py#L334)

All three functions use the same guard:

```python
owns_transaction = not conn.in_transaction
if owns_transaction:
    conn.execute("BEGIN IMMEDIATE")
```

and only `commit()` / `rollback()` when `owns_transaction` is true.

### Proven

For all three functions, when called inside a caller-owned transaction:

- they do not issue `BEGIN IMMEDIATE`
- they do not issue `COMMIT`
- they do not issue `ROLLBACK`
- they leave `conn.in_transaction == True`
- their writes remain pending and visible to the caller until the caller decides to `ROLLBACK`

#### `dual_write_registered_file()` proof

Success case output:

```text
success in_transaction True
counts 1 1 1
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback 0 0 0
```

Failure case output after forcing `record_provenance_event()` to raise:

```text
exc RuntimeError boom
failure in_transaction True
pending_counts 1 1 1
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback 0 0 0
```

Interpretation:

- On outer-transaction failure, partial writes remain pending; the function does not roll them back itself.

Existing repository test only proves the owner-transaction case:

- [`test_dual_write_registered_file_rolls_back_when_flow_fails`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_transaction_boundaries.py)

#### `resolve_or_create_identity()` proof

Success case output:

```text
success identity_id 1
success in_transaction True
pending_count 1
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback 0
```

Failure case output after patching `_create_identity()` to insert then raise:

```text
exc RuntimeError boom-after-insert
failure in_transaction True
pending_count 1
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback 0
```

Interpretation:

- On outer-transaction failure, inserted identity rows remain pending; the function does not roll them back itself.

No repository test currently proves the outer-transaction case for this function.

#### `merge_group_by_repointing_assets()` proof

Success case output:

```text
success winner 2
success in_transaction True
pending_loser (None, 2)
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback ('BP-1', None)
```

Failure case output after patching `_assert_asset_link_unique()` to raise after partial writes:

```text
exc RuntimeError post-merge failure
failure in_transaction True
pending_loser (None, 2)
pending_winner ('Artist A', 'Track A')
pending_links [(1, 2), (2, 2)]
trace_has_begin_immediate False
trace_has_commit False
trace_has_rollback False
after_caller_rollback ('BP-1', None)
```

Interpretation:

- On outer-transaction failure, merge writes remain pending; the function does not roll them back itself.

Existing repository test only proves the owner-transaction case:

- [`test_merge_group_by_repointing_assets_rolls_back_without_outer_transaction`](/Users/georgeskhawam/Projects/tagslut/tests/storage/v3/test_transaction_boundaries.py)

## A. Facts newly proven

- Fresh bootstrap and a filtered supported `v9 -> v11` migration path produce the same effective table and index schema for `asset_file`, `track_identity`, `asset_link`, and `preferred_asset`.
- That equivalence includes all seven provider unique partial indexes, confirmed by `sqlite_master`, `PRAGMA index_list`, and `PRAGMA index_xinfo`.
- `schema_migrations` is not content-equivalent: versions match, notes differ.
- Provider-duplicate repair is asymmetric:
  - schema enforcement exists for seven provider ids
  - helper-level reuse exists for those seven plus `itunes_id` and `musicbrainz_id`, and separately for `isrc`
  - duplicate discovery helper and merge automation are Beatport-specific
- Under caller-owned transactions, all three write functions avoid `BEGIN IMMEDIATE`, `COMMIT`, and `ROLLBACK`; they propagate exceptions and leave pending writes for the caller to resolve.

## B. Facts still unproven

- Full default-directory upgrade-path equivalence is not proven because [`run_pending_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py) currently fails on [`_0009_chromaprint.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/_0009_chromaprint.py).
- No proof was produced that earlier upgrade starting points below `v9` converge to the same effective schema; this note only proves `v9 -> v11`.
- No direct test proof exists for helper-level reuse behavior on `tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`, `deezer_id`, `traxsource_id`, `itunes_id`, or `musicbrainz_id`.
- No proof exists for non-Beatport provider merge automation because none was found.

## C. Smallest safe next code slice

Do not change behavior broadly. The smallest safe patch plan is:

1. Add one targeted test that exercises [`run_pending_v3()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py) against the real default migrations directory from a `v9` state and currently reproduces the `_0009_chromaprint.py` failure.
2. Patch [`_iter_migration_files()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migration_runner.py) or `_version_from_filename()` to ignore underscore-prefixed helper modules like [`_0009_chromaprint.py`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/migrations/_0009_chromaprint.py) without changing any migration semantics.
3. Add three narrow outer-transaction tests, one each for [`dual_write_registered_file()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/dual_write.py), [`resolve_or_create_identity()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/identity_service.py), and [`merge_group_by_repointing_assets()`](/Users/georgeskhawam/Projects/tagslut/tagslut/storage/v3/merge_identities.py), asserting:
   - no `BEGIN IMMEDIATE`
   - no `COMMIT`
   - no `ROLLBACK`
   - caller-visible pending writes before caller rollback
