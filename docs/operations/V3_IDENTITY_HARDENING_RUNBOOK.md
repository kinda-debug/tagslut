# V3 Identity Hardening Runbook

This runbook covers migration execution, duplicate audits, merge handling, and transaction safety for v3 identity hardening.

## Files To Know

- `tagslut/storage/v3/migration_runner.py`
- `tagslut/storage/v3/schema.py`
- `tagslut/storage/v3/migrations/0010_track_identity_provider_uniqueness.py`
- `tagslut/storage/v3/migrations/0011_track_identity_provider_uniqueness_hardening.py`
- `tagslut/storage/v3/merge_identities.py`
- `tagslut/storage/v3/backfill_identity.py`
- `tagslut/storage/v3/dual_write.py`

## Current Enforced Provider Fields

Active-only unique partial indexes exist for:

- `beatport_id`
- `tidal_id`
- `qobuz_id`
- `spotify_id`
- `apple_music_id`
- `deezer_id`
- `traxsource_id`

The uniqueness scope is:

- include row only when provider value is non-null
- exclude row when the unique-index predicate treats it as blank:
  - `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`: `TRIM(column) != ''` (SQLite default trim set; space-only is excluded, but tab/newline-only is not)
  - `apple_music_id`, `deezer_id`, `traxsource_id`: `TRIM(column, ' \t\n\r') != ''`
- include row only when `merged_into_id IS NULL`

## Current Non-Enforced Identifier Fields

No active-only unique partial index exists for:

- `isrc`
- `itunes_id`
- `musicbrainz_id`

Treat these as operator-review identifiers, not storage-enforced uniqueness keys.

Policy note (current repo behavior):

- `itunes_id` and `musicbrainz_id` participate in helper-level identity resolution (`identity_service.py`) but are not audited or uniqueness-enforced by `0010`/`0011` or the fresh schema.

## Upgrade Procedure

Run the project migration path from the repository root:

```bash
poetry run python - <<'PY'
from tagslut.storage.v3.migration_runner import run_pending_v3
print(run_pending_v3("path/to/db.sqlite"))
PY
```

Expected result:

- `0010_track_identity_provider_uniqueness.py` applies if the database is below version `10`
- `0011_track_identity_provider_uniqueness_hardening.py` applies if the database is below version `11`
- the call raises before recording the version if duplicate active provider rows block index creation

## Preflight Duplicate Audit SQL

Run these queries before applying `0010` and `0011` when operating on existing databases. They mirror what the migrations do: first apply the in-place trimming/blank-to-`NULL` updates, then group duplicates by the stored column value.

### `0010` provider set

```sql
-- Mirror 0010 normalization (SQLite TRIM default: spaces only).
UPDATE track_identity SET beatport_id = NULL WHERE beatport_id IS NOT NULL AND TRIM(beatport_id) = '';
UPDATE track_identity SET beatport_id = TRIM(beatport_id) WHERE beatport_id IS NOT NULL AND beatport_id != TRIM(beatport_id);
UPDATE track_identity SET tidal_id = NULL WHERE tidal_id IS NOT NULL AND TRIM(tidal_id) = '';
UPDATE track_identity SET tidal_id = TRIM(tidal_id) WHERE tidal_id IS NOT NULL AND tidal_id != TRIM(tidal_id);
UPDATE track_identity SET qobuz_id = NULL WHERE qobuz_id IS NOT NULL AND TRIM(qobuz_id) = '';
UPDATE track_identity SET qobuz_id = TRIM(qobuz_id) WHERE qobuz_id IS NOT NULL AND qobuz_id != TRIM(qobuz_id);
UPDATE track_identity SET spotify_id = NULL WHERE spotify_id IS NOT NULL AND TRIM(spotify_id) = '';
UPDATE track_identity SET spotify_id = TRIM(spotify_id) WHERE spotify_id IS NOT NULL AND spotify_id != TRIM(spotify_id);

WITH duplicate_groups AS (
    SELECT 'beatport_id' AS provider_column, beatport_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE beatport_id IS NOT NULL
      AND TRIM(beatport_id) != ''
      AND merged_into_id IS NULL
    GROUP BY beatport_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'tidal_id', tidal_id, COUNT(*)
    FROM track_identity
    WHERE tidal_id IS NOT NULL
      AND TRIM(tidal_id) != ''
      AND merged_into_id IS NULL
    GROUP BY tidal_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'qobuz_id', qobuz_id, COUNT(*)
    FROM track_identity
    WHERE qobuz_id IS NOT NULL
      AND TRIM(qobuz_id) != ''
      AND merged_into_id IS NULL
    GROUP BY qobuz_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'spotify_id', spotify_id, COUNT(*)
    FROM track_identity
    WHERE spotify_id IS NOT NULL
      AND TRIM(spotify_id) != ''
      AND merged_into_id IS NULL
    GROUP BY spotify_id
    HAVING COUNT(*) > 1
)
SELECT provider_column, provider_id, row_count
FROM duplicate_groups
ORDER BY provider_column, provider_id;
```

### `0011` provider set

```sql
-- Mirror 0011 normalization (explicit trim set: space/tab/newline/CR).
UPDATE track_identity SET apple_music_id = NULL WHERE apple_music_id IS NOT NULL AND TRIM(apple_music_id, ' \t\n\r') = '';
UPDATE track_identity SET apple_music_id = TRIM(apple_music_id, ' \t\n\r') WHERE apple_music_id IS NOT NULL AND apple_music_id != TRIM(apple_music_id, ' \t\n\r');
UPDATE track_identity SET deezer_id = NULL WHERE deezer_id IS NOT NULL AND TRIM(deezer_id, ' \t\n\r') = '';
UPDATE track_identity SET deezer_id = TRIM(deezer_id, ' \t\n\r') WHERE deezer_id IS NOT NULL AND deezer_id != TRIM(deezer_id, ' \t\n\r');
UPDATE track_identity SET traxsource_id = NULL WHERE traxsource_id IS NOT NULL AND TRIM(traxsource_id, ' \t\n\r') = '';
UPDATE track_identity SET traxsource_id = TRIM(traxsource_id, ' \t\n\r') WHERE traxsource_id IS NOT NULL AND traxsource_id != TRIM(traxsource_id, ' \t\n\r');

WITH duplicate_groups AS (
    SELECT 'apple_music_id' AS provider_column, apple_music_id AS provider_id, COUNT(*) AS row_count
    FROM track_identity
    WHERE apple_music_id IS NOT NULL
      AND TRIM(apple_music_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL
    GROUP BY apple_music_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'deezer_id', deezer_id, COUNT(*)
    FROM track_identity
    WHERE deezer_id IS NOT NULL
      AND TRIM(deezer_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL
    GROUP BY deezer_id
    HAVING COUNT(*) > 1
    UNION ALL
    SELECT 'traxsource_id', traxsource_id, COUNT(*)
    FROM track_identity
    WHERE traxsource_id IS NOT NULL
      AND TRIM(traxsource_id, ' \t\n\r') != ''
      AND merged_into_id IS NULL
    GROUP BY traxsource_id
    HAVING COUNT(*) > 1
)
SELECT provider_column, provider_id, row_count
FROM duplicate_groups
ORDER BY provider_column, provider_id;
```

## Failure Handling

If `0010` or `0011` fails with `duplicate active provider ids block migration ...`:

1. identify the duplicate provider field and provider value (as stored after the migration’s trim/blank-to-`NULL` updates)
2. inspect all rows with that value and `merged_into_id IS NULL`
3. resolve the duplicate set using the provider-specific guidance below
4. leave only one canonical winner active
5. rerun the migration

Do not bypass the migration by creating the unique indexes manually without resolving the duplicate set.

### Provider-Specific Resolution Guidance

Beatport duplicate blockers (`beatport_id`):

- repository helper exists: `tagslut/storage/v3/merge_identities.py`
- use `merge_group_by_repointing_assets(conn, winner_id, loser_ids, dry_run=False)` to merge a duplicate set
- merge automation is Beatport-specific by design (winner must retain a nonblank `beatport_id`; loser `beatport_id`
  is cleared; post-merge validation checks only active `beatport_id`)

Non-Beatport enforced-provider duplicate blockers (`tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`,
`deezer_id`, `traxsource_id`):

- no repository-provided provider-generic duplicate merge automation exists today
- operator-driven repair steps:
  - inspect the duplicate rows (`merged_into_id IS NULL`) for the provider value (as stored after trimming)
  - choose the canonical winner identity id
  - repair the other rows manually so only one canonical winner remains active for that provider value
  - rerun the migration

Non-enforced identifiers (`isrc`, `itunes_id`, `musicbrainz_id`):

- these are not schema-enforced uniqueness surfaces in v3
- treat duplicates for these fields as operator-review / policy-only conflicts, not migration blockers

## Canonical Duplicate Inspection SQL

Inspect active rows for one provider field:

```sql
SELECT id, identity_key, merged_into_id, beatport_id, tidal_id, qobuz_id, spotify_id,
       apple_music_id, deezer_id, traxsource_id, isrc, canonical_artist, canonical_title
FROM track_identity
WHERE merged_into_id IS NULL
  AND deezer_id IS NOT NULL
  AND TRIM(deezer_id, ' \t\n\r') = 'dz-1'
ORDER BY id;
```

Inspect merged losers for the same provider value (after trimming):

```sql
SELECT id, identity_key, merged_into_id, deezer_id
FROM track_identity
WHERE deezer_id IS NOT NULL
  AND TRIM(deezer_id, ' \t\n\r') = 'dz-1'
ORDER BY merged_into_id IS NULL DESC, id;
```

## Merge Procedure

Repository merge implementation:

- `tagslut/storage/v3/merge_identities.py`
- main write function: `merge_group_by_repointing_assets(conn, winner_id, loser_ids, dry_run=False)`

Operational rules:

- the winner must be active and must retain a nonblank `beatport_id`
- losers must not already be merged
- the merge function repoints assets, copies missing canonical fields, marks losers with `merged_into_id`, clears loser `beatport_id`, and deletes loser `preferred_asset` rows
- post-merge validation rejects any remaining active duplicate `beatport_id`

Operator expectation:

- merged losers do not block `0010` or `0011`
- canonical winners are the only rows that participate in provider uniqueness

## Transaction-Boundary Rules

### Dual write

`tagslut/storage/v3/dual_write.py:dual_write_registered_file()`:

- starts `BEGIN IMMEDIATE` only when no outer transaction exists
- rolls back its own work on any downstream failure

Use this behavior when debugging a registration failure:

- if the call raised and no outer transaction existed, expect `asset_file`, `track_identity`, and `asset_link` to remain unchanged

### Merge

`tagslut/storage/v3/merge_identities.py:merge_group_by_repointing_assets()`:

- starts `BEGIN IMMEDIATE` only when no outer transaction exists
- rolls back all writes on validation failure after partial updates

Use this behavior when debugging a merge failure:

- if the call raised and no outer transaction existed, expect loser `merged_into_id`, repointed `asset_link`, copied canonical fields, and `preferred_asset` cleanup to be fully reverted

### Backfill

`tagslut/storage/v3/backfill_identity.py` execute mode:

- opens an immediate transaction per active batch
- commits every `--commit-every N`
- writes checkpoints every `--checkpoint-every N`
- resumes after checkpoints with `--resume-from-file-id`

Use this behavior for large backfills:

- keep `--commit-every 1` for the safest row-by-row execution
- increase batch size only when the database is stable and you can tolerate batch rollback

## Post-Migration Verification

Check applied versions:

```sql
SELECT version, note
FROM schema_migrations
WHERE schema_name = 'v3'
  AND version IN (10, 11)
ORDER BY version;
```

Check the indexes exist:

```sql
SELECT name, sql
FROM sqlite_master
WHERE type = 'index'
  AND name IN (
    'uq_track_identity_active_beatport_id',
    'uq_track_identity_active_tidal_id',
    'uq_track_identity_active_qobuz_id',
    'uq_track_identity_active_spotify_id',
    'uq_track_identity_active_apple_music_id',
    'uq_track_identity_active_deezer_id',
    'uq_track_identity_active_traxsource_id'
  )
ORDER BY name;
```

Check integrity:

```sql
PRAGMA foreign_key_check;
PRAGMA integrity_check;
```

Expected result:

- `foreign_key_check` returns no rows
- `integrity_check` returns `ok`

## Fresh-Schema Verification

On a database created with `create_schema_v3()`:

- versions `10` and `11` must already exist in `schema_migrations`
- all seven active-provider unique partial indexes must already exist
- `run_pending_v3()` must not attempt to reapply `0010` or `0011`
