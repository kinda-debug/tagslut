# Capture TIDAL native audio fields (BPM/key/replayGain/readiness) into v3 `track_identity`

## Do not recreate existing files. Do not modify schema.py directly.

## Summary

- Add new nullable v3 columns on `track_identity` for TIDAL-native audio fields.
- Extract + normalize those fields from the TIDAL provider response (with Camelot mapping).
- Skip ReccoBeats ISRC calls when a TIDAL match already provides BPM.
- Persist extracted TIDAL-native fields onto the linked v3 `track_identity` row during
  enrichment writes (best-effort; no behavior change if v3 tables/columns aren't present).

## Step 1 — V3 migration 0016

File: `tagslut/storage/v3/migrations/0016_tidal_audio_fields.sql`
(Note: `0015_*` already exists in this repo — use 0016.)

```sql
ALTER TABLE track_identity ADD COLUMN tidal_bpm REAL;
ALTER TABLE track_identity ADD COLUMN tidal_key TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_key_scale TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_camelot TEXT;
ALTER TABLE track_identity ADD COLUMN replay_gain_track REAL;
ALTER TABLE track_identity ADD COLUMN replay_gain_album REAL;
ALTER TABLE track_identity ADD COLUMN tidal_dj_ready INTEGER;
ALTER TABLE track_identity ADD COLUMN tidal_stem_ready INTEGER;
INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
  VALUES ('v3', 16, '0016_tidal_audio_fields.sql');
```

## Step 2 — Camelot mapping

Create `tagslut/enrichment/__init__.py` (empty, marks package).
Create `tagslut/enrichment/camelot.py` with pure function:

```python
def to_camelot(key: str, scale: str) -> str | None:
    """
    Convert TIDAL key/keyScale to Camelot notation.
    Case-insensitive. Returns None for unknown inputs without raising.
    """
```

Full 24-entry mapping. Enharmonic pairs map to the same slot. Major = B suffix,
minor = A suffix.

- C/MAJOR=8B, G/MAJOR=9B, D/MAJOR=10B, A/MAJOR=11B, E/MAJOR=12B, B/MAJOR=1B
- FSharp/MAJOR=Gb/MAJOR=2B, Db/MAJOR=CSharp/MAJOR=3B, Ab/MAJOR=GSharp/MAJOR=4B
- Eb/MAJOR=DSharp/MAJOR=5B, Bb/MAJOR=ASharp/MAJOR=6B, F/MAJOR=7B
- A/MINOR=8A, E/MINOR=9A, B/MINOR=10A, FSharp/MINOR=Gb/MINOR=11A
- Db/MINOR=CSharp/MINOR=12A, Ab/MINOR=GSharp/MINOR=1A, Eb/MINOR=DSharp/MINOR=2A
- Bb/MINOR=ASharp/MINOR=3A, F/MINOR=4A, C/MINOR=5A, G/MINOR=6A, D/MINOR=7A

## Step 3 — Provider model + TIDAL extraction

Extend `tagslut/metadata/models/types.py:ProviderTrack` with new optional fields
(all default `None`):
- `tidal_bpm`, `tidal_key`, `tidal_key_scale`, `tidal_camelot`
- `replay_gain_track`, `replay_gain_album`
- `tidal_dj_ready`, `tidal_stem_ready`

Update `tagslut/metadata/providers/tidal.py` in `_normalize_track()` to populate:
- `tidal_bpm` from `attributes["bpm"]` (float coercion); keep existing `bpm` intact
- `tidal_key` from `attributes["key"]`
- `tidal_key_scale` from `attributes["keyScale"]`
- `tidal_camelot` via `to_camelot(tidal_key, tidal_key_scale)` when both present
- `tidal_dj_ready` / `tidal_stem_ready` from `attributes["djReady"]` /
  `attributes["stemReady"]` (store as `0/1` int when present)
- `replay_gain_track` / `replay_gain_album` by best-effort extraction from track
  payload (handle float-or-dict shapes; keep `None` if absent)
- Only add a fallback `GET https://api.tidal.com/v1/tracks/{id}` call if the v2
  payload lacks required fields; reuse `_make_request()` + existing token loading;
  include `time.sleep(0.2)` after the fallback call.

## Step 4 — Enrichment routing: skip ReccoBeats when TIDAL BPM exists

Update `tagslut/metadata/pipeline/stages.py` Stage 1 (ISRC loop):
- Before calling provider `reccobeats`, check whether `matches` already contains
  a `tidal` match with non-null BPM (`m.tidal_bpm` or `m.bpm`).
- If so, log a skip and do not call ReccoBeats for that file.

## Step 5 — Persist new fields to v3 `track_identity` on write

Update `tagslut/metadata/store/db_writer.py:update_database()`:

- After updating `files`, attempt to resolve a linked v3 identity for `result.path`:
  `asset_file(path) → asset_link(active=1) → track_identity(id)`
- Select the "best" TIDAL match from `result.matches` (prefer `EXACT` then `STRONG`,
  otherwise first TIDAL match).
- Build an UPDATE that:
  - Writes only non-`None` values.
  - Uses `col = COALESCE(col, ?)` (fill-if-null) for all new columns to avoid
    clobbering existing values.
  - Updates `track_identity.updated_at` (and `enriched_at` if that's the repo's
    marker for identity-level enrichment) only when an identity row is found.
- If v3 tables or the new columns don't exist, skip silently (preserves current
  behavior outside v3-enabled DBs).

## Test plan

`tests/metadata/test_tidal_camelot.py`:
- All 24 combos map correctly
- Enharmonic pairs map to same Camelot slot
- Unknown inputs return `None` without raising

`tests/metadata/test_tidal_native_fields.py` — monkeypatch `TidalProvider._make_request`:
- Payload includes bpm/key/keyScale/readiness/replayGain → all new fields populated,
  `tidal_camelot` correct
- Fields missing → all new fields `None`, no exception

`tests/test_enrichment_cascade.py` — extend with FakeProvider for `reccobeats`:
- When TIDAL ISRC match includes BPM, `reccobeats.search_by_isrc()` never called

`tests/storage/v3/test_migration_0016.py`:
- `create_schema_v3(conn)` then `run_pending_v3(conn)` → assert new columns exist
  on `track_identity`

`tests/test_db_writer.py` — extend with fixture DB containing v2 + v3 tables +
linked identity, run v3 migrations, call `update_database()` with TIDAL result:
- New `track_identity` columns populated
- Pre-existing non-null values not overwritten

## Commit

`feat(enrichment): capture tidal native bpm, key, replaygain, dj-ready fields`
