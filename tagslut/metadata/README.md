<!-- Status: Active document. Reviewed 2026-03-09. Historical or superseded material belongs in docs/archive/. -->

# Metadata Package

This package handles metadata enrichment and provider resolution for FLAC files.

Start here:
- `poetry run tagslut index enrich --help` — active enrichment command help.
- `docs/SCRIPT_SURFACE.md` — canonical command surface and workflow ownership.
- `docs/archive/ (historical — see docs/archive/)METADATA_WORKFLOW.md` — archived legacy metadata workflow notes.

Writeback contract:
- Enrichment writes provider snapshots to `library_track_sources`, supporting both
  legacy `service/service_track_id` and v3 `provider/provider_track_id` shapes.
- Linked identities are resolved through `asset_file.path -> asset_link.identity_id`.
- `track_identity.canonical_*` fields are filled null-safely; existing identity
  metadata is not overwritten by enrichment writeback.
- FLAC writeback reads identity fields first and falls back to `files.canonical_*`
  only when the linked identity field is blank.

## Supported Providers

| Provider   | Status   | Auth                 | Key Features                                      |
|------------|----------|----------------------|---------------------------------------------------|
| Beatport   | Active   | Bearer token/scraping| BPM, key, genre, sub-genre, label, ISRC           |
| TIDAL      | Active   | Device authorization | ISRC, hi-res indicators, lyrics availability, native BPM/key/replayGain/readiness |
| Qobuz      | Active   | App credentials + user token | ISRC/text lookup, album metadata, artwork, booklet goodies |

**Note:** Active enrichment routing now includes Beatport, TIDAL, and Qobuz. Qobuz remains non-authoritative for identity promotion unless corroborated; see `tagslut/storage/v3/provider_evidence.py` for the evidence gate.

<!-- Future agents: Do not treat legacy/future providers as active without explicit contract change. -->

## Genre Normalization

Genre and style metadata is normalized using centralized rules for consistency across enrichment and tagging workflows.

**Core Module:** `genre_normalization.py`

- `GenreNormalizer` class: Centralized genre/style processing
  - Pluggable rules JSON mapping for custom hierarchies
  - Cascade priority: `GENRE_PREFERRED` → `SUBGENRE` → `GENRE` → `GENRE_FULL`
  - Beatport-compatible output: `GENRE`, `SUBGENRE`, `GENRE_PREFERRED`, `GENRE_FULL`

**Workflows:**
- `tools/review/normalize_genres.py` — Normalize and backfill DB with canonical genre values
- `tools/review/tag_normalized_genres.py` — Apply normalized genre tags directly to FLAC files

Both scripts import `GenreNormalizer` to ensure consistent normalization logic.

**Rules Format:**
```json
{
  "genre_map": {
    "House Music": "House",
    "Tech House": "Tech House",
    "..." : "..."
  },
  "style_map": {
    "Soulful House": "Soulful",
    "Deep Tech": "Deep Tech",
    "..." : "..."
  }
}
```

See `docs/archive/ (historical — see docs/archive/)Beatport Genres and Sub-Genres.md` for complete Beatport taxonomy.

## Key Modules

- `enricher.py` — orchestrates resolution and DB updates
- `genre_normalization.py` — shared genre/style processing (centralized DRY utility)
- `models/types.py` — data structures (ProviderTrack, EnrichmentResult, LocalFileInfo)
- `models/precedence.py` — canonical selection rules
- `auth.py` — token management
- `providers/` — provider implementations:
  - `beatport.py` — Beatport V4 API + web scraping (returns genre/sub_genre)
  - `tidal.py` — Tidal API
  - `qobuz.py` — Qobuz API metadata/artwork/booklet-goodies support
