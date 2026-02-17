# Metadata Package

This package handles metadata enrichment and provider resolution for FLAC files.

Start here:
- `poetry run tagslut index enrich --help` — active enrichment command help.
- `docs/SCRIPT_SURFACE.md` — canonical command surface and workflow ownership.
- `docs/archive/legacy-workflows-2026-02-09/METADATA_WORKFLOW.md` — archived legacy metadata workflow notes.

## Supported Providers

| Provider | Auth | Key Features |
|----------|------|--------------|
| Spotify | Client credentials | Audio features (energy, danceability), BPM, key |
| Beatport | Bearer token or web scraping | BPM, key, genre, sub-genre, label, ISRC |
| Qobuz | Email/password | Hi-res quality info, genre, label, composer |
| Tidal | Device authorization | Hi-res indicators, lyrics availability |
| Apple Music | Dynamic (auto-extracted) | ISRC, composer, credits, lyrics, classical metadata |
| iTunes | None (public API) | Basic metadata, genre, artwork |

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

See `docs/archive/inactive-root-docs-2026-02-09/Beatport Genres and Sub-Genres.md` for complete Beatport taxonomy.

## Key Modules

- `enricher.py` — orchestrates resolution and DB updates
- `genre_normalization.py` — shared genre/style processing (centralized DRY utility)
- `models/types.py` — data structures (ProviderTrack, EnrichmentResult, LocalFileInfo)
- `models/precedence.py` — canonical selection rules
- `auth.py` — token management
- `providers/` — provider implementations:
  - `spotify.py` — Spotify Web API
  - `beatport.py` — Beatport V4 API + web scraping (returns genre/sub_genre)
  - `qobuz.py` — Qobuz API
  - `tidal.py` — Tidal API
  - `apple_music.py` — Apple Music API (dynamic token)
  - `itunes.py` — iTunes Search API (public)
