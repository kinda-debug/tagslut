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

## Key Modules

- `enricher.py` — orchestrates resolution and DB updates
- `models/types.py` — data structures (ProviderTrack, EnrichmentResult)
- `models/precedence.py` — canonical selection rules
- `auth.py` — token management
- `providers/` — provider implementations:
  - `spotify.py` — Spotify Web API
  - `beatport.py` — Beatport V4 API + web scraping
  - `qobuz.py` — Qobuz API
  - `tidal.py` — Tidal API
  - `apple_music.py` — Apple Music API (dynamic token)
  - `itunes.py` — iTunes Search API (public)
