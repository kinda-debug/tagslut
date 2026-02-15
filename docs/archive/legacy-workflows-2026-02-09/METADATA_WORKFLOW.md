# Metadata Enrichment Workflow

This document explains the metadata subsystem end-to-end: what it does, how it decides, how it writes to the DB, and how to run it with or without a database.

## 1) Overview

Tudehe metadata subsystem enriches FLAC files with canonical metadata sourced from multiple providers (Spotify, Beatport, Qobuz, Tidal, Apple Music, iTunes). It is used for two primary goals:

- **Recovery mode**: validate file health by comparing local duration to provider duration.
- **Hoarding mode**: collect rich DJ metadata (BPM, key, genre, label, artwork, etc.).

It is designed to be **deterministic**, **resumable**, and **non-destructive by default**.

## 2) High-Level Flow

```
FLAC files on disk
    │
    ├─(scan)→ files table populated (path, duration, tags → metadata_json, flac_ok, etc.)
    │
    └─(enrich)→ resolve identity → fetch provider data → select canonical values
                     │
                     └─(optional) write canonical fields to DB
```

Two operational modes are supported:

- **Recovery**: focuses on duration validation and health status.
- **Hoarding**: focuses on rich metadata and requires higher match confidence.
- **Both**: writes everything from both modes.

## 3) Core Concepts

### 3.1 LocalFileInfo (input)
`LocalFileInfo` is a lightweight structure that represents a file’s identity hints:

- path
- measured_duration_s (from ffprobe / scan)
- tag_artist / tag_title / tag_album / tag_isrc / tag_label / tag_year

When using the DB-backed workflow, these come from `files.metadata_json` + `files.duration`. In standalone mode, they’re pulled directly from tags on disk.

### 3.2 EnrichmentResult (output)
`EnrichmentResult` stores canonical values and all provider matches for auditing. Canonical values are chosen using precedence rules defined in `tagslut/metadata/models.py`.

Examples of canonical fields:
- canonical_title / canonical_artist / canonical_album
- canonical_isrc
- canonical_duration (+ source)
- canonical_bpm / canonical_key / canonical_genre / canonical_label
- spotify audio features (energy, danceability, etc.)
- canonical_album_art_url

### 3.3 Match Confidence
Matches are scored and categorized into confidence tiers. Resolution prefers exact/strong matches before weaker ones, and the acceptance thresholds differ by mode (recovery vs hoarding).

## 4) Resolution Strategy (Enricher.resolve_file)

The resolution pipeline is deliberately simple and debuggable:

1. **ISRC search** (highest confidence)
2. **Artist + title search**
3. **Title-only fallback** (lenient, duration-weighted)

Each provider returns tracks that are scored using duration and string matching. The best matches are carried forward for canonical selection.

## 5) Canonical Selection (Cascade Rules)

When multiple providers return data, canonical values are selected using precedence lists. Example precedence (from `metadata/models/precedence.py`):

- Duration: `beatport → qobuz → tidal → apple_music → spotify → itunes`
- BPM/Key: `beatport → spotify`
- Title/Artist/Album: `qobuz → tidal → apple_music → beatport → spotify → itunes`
- Artwork: `qobuz → tidal → apple_music → spotify → beatport → itunes`
- Composer: `apple_music → qobuz → tidal → spotify`
- ISRC: `beatport → apple_music → qobuz → tidal → spotify`

These rules are centralized in `tagslut/metadata/models/precedence.py` so changes are deterministic and traceable.

## 6) Database Fields Written

When **--execute** is used, enrichment writes to the `files` table in SQLite. Which fields are written depends on mode:

- **Recovery**: duration and health evaluation fields (`canonical_duration`, `metadata_health`, `metadata_health_reason`, etc.)
- **Hoarding**: full metadata fields (`canonical_bpm`, `canonical_key`, `canonical_genre`, artwork URLs, etc.)
- **Both**: all of the above

All writes are centralized in `Enricher.update_database`.

## 7) CLI Usage

### 7.1 DB-backed (normal)

```
tagslut metadata enrich --db /path/to/music.db --recovery --execute
```

Filter by path pattern and zones:

```
tagslut metadata enrich --db /path/to/music.db \
  --recovery --path "/Volumes/Music/DJ/%" --zones accepted,staging --execute
```

### 7.2 Standalone (no DB)

Single file:

```
tagslut enrich-file --standalone --file /path/to/file.flac --providers beatport,spotify
```

Directory:

```
tagslut metadata enrich --standalone --path /path/to/flacs --providers beatport,spotify
```

Standalone mode reads tags directly from disk and **never writes to a DB**.

## 8) Authentication & Tokens

Tokens are stored in `~/.config/tagslut/tokens.json` by default. Supported flows:

- **Spotify**: client credentials
- **Beatport**: client credentials (public client ID) or web scraping fallback
- **Tidal**: device authorization (refresh token)
- **Qobuz**: email/password
- **Apple Music**: no configuration required (bearer token extracted dynamically from web app)
- **iTunes**: no auth (public API)

Initialize or check tokens:

```
tagslut metadata auth-init

tagslut metadata auth-status
```

### Apple Music Provider

The Apple Music provider extracts a bearer token dynamically from the Apple Music web application. No manual configuration is required. It provides rich metadata including:

- ISRC, UPC, copyright
- Composer and credits
- Genre, label, release date
- High-resolution artwork
- Classical metadata (work, movement)
- Lyrics (TTML format)

## 9) Supporting Scripts

The metadata directory also contains provider-specific utilities:

- `beatport_harvest_my_tracks.sh` / `beatport_import_my_tracks.py`: ingest a Beatport “My Tracks” dump
- `spotify_partner_tokens.py`: helper for Spotify partner tokens

These scripts are optional and are not required for the normal enrichment workflow.

## 10) Troubleshooting

Common issues:

- **No matches**: check tags (artist/title), verify provider tokens, or try a different provider order.
- **Token expired**: run `tagslut metadata auth-status` to refresh supported providers.
- **Unexpected canonical values**: check precedence rules in `metadata/models.py` and match confidence in `metadata/providers/base.py`.

## 11) Code Map

- `tagslut/metadata/enricher.py` — Orchestrates the entire workflow.
- `tagslut/metadata/models.py` — Data structures + canonical precedence rules.
- `tagslut/metadata/auth.py` — Token management.
- `tagslut/metadata/providers/` — Provider implementations.
- `tagslut/cli/main.py` — CLI entry points.

---

If you want deeper refactoring (module splits, provider isolation, new APIs), we can map a phased plan next.
