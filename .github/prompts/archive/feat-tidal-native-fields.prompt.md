# Implement: TIDAL native fields → v3 `track_identity`

## Do not recreate existing files. Do not modify schema.py directly.

## Summary

- Add v3 migration `0016` with nullable `track_identity` columns for TIDAL-native
  BPM/key/Camelot/replayGain/readiness.
- Add Camelot mapping utility (`to_camelot`) and wire into TIDAL normalization.
- Extend `ProviderTrack` to carry the new native fields and persist them (best-effort)
  to v3 identity rows during `update_database()`.
- Skip ReccoBeats ISRC lookup when a TIDAL ISRC match already provides BPM.

## Step 1 — V3 migration `0016`

Create `tagslut/storage/v3/migrations/0016_tidal_audio_fields.sql`:
- Add nullable columns: `tidal_bpm`, `tidal_key`, `tidal_key_scale`, `tidal_camelot`,
  `replay_gain_track`, `replay_gain_album`, `tidal_dj_ready`, `tidal_stem_ready`
- Record migration: `schema_migrations (schema_name='v3', version=16,
  note='0016_tidal_audio_fields.sql')`

## Step 2 — Camelot mapping

Create `tagslut/enrichment/__init__.py` (empty).
Create `tagslut/enrichment/camelot.py`:
- `to_camelot(key: str, scale: str) -> str | None`
- Case-insensitive normalization; return `None` for unknowns without raising
- Full 24-entry mapping with enharmonic equivalence:
  - C/MAJOR=8B, G/MAJOR=9B, D/MAJOR=10B, A/MAJOR=11B, E/MAJOR=12B, B/MAJOR=1B
  - FSharp/MAJOR=Gb/MAJOR=2B, Db/MAJOR=CSharp/MAJOR=3B, Ab/MAJOR=GSharp/MAJOR=4B
  - Eb/MAJOR=DSharp/MAJOR=5B, Bb/MAJOR=ASharp/MAJOR=6B, F/MAJOR=7B
  - A/MINOR=8A, E/MINOR=9A, B/MINOR=10A, FSharp/MINOR=Gb/MINOR=11A
  - Db/MINOR=CSharp/MINOR=12A, Ab/MINOR=GSharp/MINOR=1A, Eb/MINOR=DSharp/MINOR=2A
  - Bb/MINOR=ASharp/MINOR=3A, F/MINOR=4A, C/MINOR=5A, G/MINOR=6A, D/MINOR=7A

## Step 3 — ProviderTrack model

Update `tagslut/metadata/models/types.py:ProviderTrack` to add optional fields
(default `None`):
- `tidal_bpm`, `tidal_key`, `tidal_key_scale`, `tidal_camelot`
- `replay_gain_track`, `replay_gain_album`
- `tidal_dj_ready`, `tidal_stem_ready`

## Step 4 — TIDAL normalization + extraction

Update `tagslut/metadata/providers/tidal.py`:
- Import `time` and `to_camelot`.
- In `_normalize_track()` populate the new fields from v2 `attributes` with safe
  coercions and best-effort replayGain parsing.
- If v2 is missing at least one of `bpm`, `key`, `keyScale`, `djReady`, `stemReady`,
  `replayGain`, do a conditional v1 fallback:
  - `GET {V1_BASE_URL}/tracks/{id}` via `_make_request()`, then `time.sleep(0.2)`
  - Merge any found values into native fields; never raise on unexpected shapes.

## Step 5 — Pipeline: skip ReccoBeats when TIDAL BPM exists

Update `tagslut/metadata/pipeline/stages.py` Stage 1 ISRC loop:
- Before calling `reccobeats.search_by_isrc()`, if `matches` already includes a
  `tidal` match with BPM present (`getattr(m, "tidal_bpm", None)` or `m.bpm`),
  log a skip and `continue`.

## Step 6 — Persist native fields to v3 identity on write

Update `tagslut/metadata/store/db_writer.py:update_database()`:
- After the `files` update, attempt v3 identity update (best-effort).
- If any of `asset_file`, `asset_link`, `track_identity` missing: return without error.
- Resolve identity id via `asset_file(path) → asset_link (active=1 if column exists)
  → track_identity(id)`.
- Pick best TIDAL match from `result.matches` (prefer `EXACT`, then `STRONG`, else
  first TIDAL).

- Build dynamic `UPDATE track_identity ... WHERE id = ?`:
  - Only non-`None` inputs and only if the column exists.
  - Use `col = COALESCE(col, ?)` for each native field (fill-if-null).
  - If writing at least one native field:
    - Set `updated_at = CURRENT_TIMESTAMP` when column present.
    - Set `enriched_at = COALESCE(enriched_at, CURRENT_TIMESTAMP)` when column present.
- Wrap the v3 block in `try/except sqlite3.Error` — skip silently on any error.

## Test plan (targeted pytest)

- Add `tests/metadata/test_tidal_camelot.py` (24 mappings, enharmonics, unknown→None).
- Add `tests/metadata/test_tidal_native_fields.py` (monkeypatch `_make_request` for
  v2-only + v2-missing/v1-missing cases).
- Update `tests/test_enrichment_cascade.py` (Fake `reccobeats`; assert ISRC call
  skipped when TIDAL BPM present).
- Add `tests/storage/v3/test_migration_0016.py` (run v3 schema + pending migrations;
  assert new columns exist).
- Update `tests/test_db_writer.py` (fixture DB with v2 `files` + v3 tables + linked
  identity; run v3 migrations; call `update_database()`; assert populate + no
  overwrite of existing non-null values).

Run:
```
pytest tests/metadata/test_tidal_camelot.py \
       tests/metadata/test_tidal_native_fields.py \
       tests/test_enrichment_cascade.py \
       tests/storage/v3/test_migration_0016.py \
       tests/test_db_writer.py
```

## Assumptions

- v3 tables live in the same SQLite DB file passed to `update_database()`.
- `track_identity.enriched_at` is the identity-level enrichment marker; fill only if
  null and only when writing at least one native field.

## Commit

`feat(enrichment): capture tidal native bpm, key, replaygain, dj-ready fields`
