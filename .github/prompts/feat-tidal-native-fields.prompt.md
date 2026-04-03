# feat(enrichment): capture TIDAL native BPM, key, and replayGain fields

## Do not recreate existing files. Do not modify schema.py directly.

## Context

TIDAL's track API returns `bpm`, `key`, `keyScale`, `replayGain` (track + album),
`djReady`, and `stemReady` natively in the track info response. Tagslut's current
enrichment pipeline does not capture these fields. ReccoBeats is used as the BPM/key
source, but for TIDAL-sourced tracks TIDAL's own values should take precedence.
ReccoBeats must remain as fallback only for tracks where TIDAL fields are absent.

TIDAL key format: `key` is an enum string (`"C"`, `"CSharp"`, `"Db"`, `"FSharp"`,
`"Ab"`, etc.), `keyScale` is `"MAJOR"` or `"MINOR"`. These are unambiguous and require
no Unicode normalization. Do not confuse with Beatport's traditional notation format.

## Do not touch

- `tagslut/storage/v3/schema.py` — use a new migration file only
- Any existing ReccoBeats provider logic — adjust call priority only, do not remove
- `providers.toml` structure — add entries, do not restructure
- `tools/get-intake` interface

## Step 1 — Read existing code first

Before writing any code, read:
1. The existing TIDAL provider / tiddl auth bridge (search for where `tiddl` or
   `auth.json` is referenced in the enrichment path)
2. The ReccoBeats provider to understand the exact field contract it fulfills
3. Migration 0014 to understand current schema tail and migration registration pattern

## Step 2 — Create migration 0015

File: `tagslut/storage/v3/migrations/0015_tidal_audio_fields.sql`

```sql
ALTER TABLE track_identity ADD COLUMN tidal_bpm REAL;
ALTER TABLE track_identity ADD COLUMN tidal_key TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_key_scale TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_camelot TEXT;
ALTER TABLE track_identity ADD COLUMN replay_gain_track REAL;
ALTER TABLE track_identity ADD COLUMN replay_gain_album REAL;
ALTER TABLE track_identity ADD COLUMN tidal_dj_ready INTEGER;
ALTER TABLE track_identity ADD COLUMN tidal_stem_ready INTEGER;
```

All columns nullable. Register in the migrations table using the same pattern as 0014.

## Step 3 — Camelot mapping

Create `tagslut/enrichment/camelot.py` (new file).

Implement one pure function `to_camelot(key: str, scale: str) -> str | None`.

Full 24-entry lookup table. TIDAL uses `"FSharp"` and `"Gb"` as distinct values for
enharmonic equivalents — map both to the same Camelot slot. Major = B suffix
(outer wheel), minor = A suffix (inner wheel).

Standard mapping:
- C/MAJOR=8B, G/MAJOR=9B, D/MAJOR=10B, A/MAJOR=11B, E/MAJOR=12B, B/MAJOR=1B
- FSharp/MAJOR=Gb/MAJOR=2B, Db/MAJOR=CSharp/MAJOR=3B, Ab/MAJOR=GSharp/MAJOR=4B
- Eb/MAJOR=DSharp/MAJOR=5B, Bb/MAJOR=ASharp/MAJOR=6B, F/MAJOR=7B
- A/MINOR=8A, E/MINOR=9A, B/MINOR=10A, FSharp/MINOR=Gb/MINOR=11A
- Db/MINOR=CSharp/MINOR=12A, Ab/MINOR=GSharp/MINOR=1A, Eb/MINOR=DSharp/MINOR=2A
- Bb/MINOR=ASharp/MINOR=3A, F/MINOR=4A, C/MINOR=5A, G/MINOR=6A, D/MINOR=7A

Return None for unrecognised input without raising.

## Step 4 — TIDAL provider field extraction

In the TIDAL provider's metadata extraction path, after fetching track data, extract
and return:

- `tidal_bpm` ← `track.get("bpm")` (float or None)
- `tidal_key` ← `track.get("key")` (string or None)
- `tidal_key_scale` ← `track.get("keyScale")` (string or None)
- `tidal_camelot` ← `to_camelot(key, scale)` if both present, else None
- `replay_gain_track` ← `trackReplayGain` from stream endpoint response if available
- `replay_gain_album` ← `albumReplayGain` from stream endpoint response if available
- `tidal_dj_ready` ← `int(track["djReady"])` if present, else None
- `tidal_stem_ready` ← `int(track["stemReady"])` if present, else None

If the TIDAL provider does not currently issue a track detail request (i.e. these
fields are not already in the response object being processed), check whether tiddl
surfaces them via the existing auth bridge. If not, add a lightweight direct call to
`https://api.tidal.com/v1/tracks/{tidal_id}` using the loaded tiddl token. Do not
build a new auth client — reuse the existing token loading path. Add a 0.2s delay
after this request.

## Step 5 — Enrichment priority order

In the metadata router / enrichment orchestrator, update BPM/key resolution to:

1. If `tidal_bpm IS NOT NULL` for the row → skip ReccoBeats call entirely
2. Otherwise → call ReccoBeats as before

Do not remove ReccoBeats. Do not change the ReccoBeats provider.

## Step 6 — Storage write

In the enrichment write path (where `enriched_at` is updated on `track_identity`),
also write the new fields via targeted UPDATE. Only write non-None values. Never
overwrite an existing non-null value with None.

## Step 7 — Tests

`tests/enrichment/test_camelot.py`:
- All 24 key/scale combos produce correct output
- Enharmonic pairs (FSharp vs Gb, etc.) map to the same slot
- Unknown input returns None without raising

`tests/providers/test_tidal_fields.py`:
- Mock a TIDAL track response containing bpm/key/keyScale; assert all fields extracted
- Mock a response missing these fields; assert None values returned, no exception
- Assert ReccoBeats is NOT called when `tidal_bpm` is already populated

## Commit

`feat(enrichment): capture tidal native bpm, key, replaygain, djReady fields`
