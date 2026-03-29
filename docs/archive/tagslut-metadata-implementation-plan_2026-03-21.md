# tagslut: What's Done, What's Next

**Updated:** 2026-03-21

## Done

- `.gitignore` hardened, `docs/reference/README.md` created
- Contract docs written (`docs/contracts/`)
- TIDAL transport audit (inline comments in `tidal.py`)
- Beatport auth fallback log level upgraded to WARNING
- Confidence normalization: enum in dataclasses, canonical dict in `types.py`
- Postman collection built (`postman/collections/tagslut-beatport-api.postman_collection.json`)

## Active Now

Build a modular downloader + tagger. Standalone script, not wired into the full CLI.

### What it does

1. Takes a TIDAL playlist URL (or CSV of ISRCs)
2. For each track: resolves ISRC via Beatport, downloads via TIDAL
3. Tags the file with merged vendor metadata (Beatport genre/key/label + TIDAL quality)
4. Outputs tagged FLACs to a target directory

### Constraints

- Uses existing `TidalProvider` and `BeatportProvider` directly
- Does NOT require `identity_service` or Supabase — file-based output only
- Auth: TIDAL PKCE token + Beatport client credentials (both working)
- Provenance: vendor fields stay separate in tags, no cross-contamination

### Year tagging policy

**Electronic music (Beatport catalog):** Use Beatport `publish_date` as `date`. This is the release date that matters for DJ library organization. `originaldate` left empty unless manually enriched later.

**Non-electronic music (reissues, back catalog):** Prefer original release year as `date` for folder naming. Reissue date stored as `date` only if the release is a new compilation, best-of, or remix album -- not a straight reissue of existing material. A 1975 Led Zeppelin track reissued in 2015 should file under `(1975)`, not `(2015)`.

**Implementation:** The download script uses Beatport/TIDAL publish date by default. A future enrichment pass (MusicBrainz or manual) can backfill `originaldate` for non-electronic reissues. The `final_library_layout.py` year key priority (`date`, `originaldate`, `year`) already supports this -- once `originaldate` is populated and prioritized, folder naming corrects automatically.

**Not implemented yet.** This is a tagging policy, not a code change. Recorded here so it doesn't get lost.

## Backlog (touch when relevant)

- Phase 2: archive sweep + provider scope cleanup
- Phase 3d: Beatport `/store/{isrc}/` endpoint test (Postman ready)
- Phase 3g: write-path atomicity audit
- Phase 4: test hardening
- Phase 5: bidirectional enrichment
