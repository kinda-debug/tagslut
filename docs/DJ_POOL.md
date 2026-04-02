<!-- Status: Active. Updated 2026-04-02 to reflect M3U model. -->

# DJ Pool

## Current model

The DJ pool is a single M3U playlist file, not a separate folder.

**Location:** `$MP3_LIBRARY/dj_pool.m3u`

## How it works

- `ts-get <url> --dj` downloads tracks and appends their MP3 paths to two M3U files:
  - A per-batch M3U named after the playlist/album, in the album folder
  - The global accumulating `$MP3_LIBRARY/dj_pool.m3u`
- Import either M3U into Rekordbox
- Build crates in Rekordbox
- Synchronize to USB before gig

## Rekordbox workflow

1. Import `$MP3_LIBRARY/dj_pool.m3u` into Rekordbox
2. Rekordbox analyzes BPM/beatgrid/waveform (this is the real BPM source for DJ use)
3. Build crates manually
4. Synchronize to USB before gig

## What DJ_LIBRARY is

`/Volumes/MUSIC/DJ_LIBRARY` is a legacy folder containing MP3s accumulated
before the M3U model was adopted. It is not actively written to. Its contents
are being registered into the DB and will be enriched via `ts-enrich`.

## What is NOT the DJ pool

- The 4-stage pipeline (backfill/validate/XML emit) is retired
- `DJ_LIBRARY` as a destination folder is retired
- `tagslut dj pool-wizard` is a legacy command, not the active workflow
- Rekordbox XML emit is not the active workflow

## Related

- `docs/DOWNLOAD_STRATEGY.md` — source selection
- `docs/CREDENTIAL_MANAGEMENT.md` — token management
