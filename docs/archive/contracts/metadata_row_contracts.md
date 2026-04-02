# Metadata Row Contracts

**Status:** Normative  
**Anchored to:** commit `a060a2b` + local repo state 2026-03-19  
**Source of truth:** `tagslut/metadata/models/types.py`

---

## Overview

The batch CSV interface uses fixed-column dataclasses and header tuples defined in `types.py`. These are the stable contracts for the two enrichment flows.

**CSV is the batch interface. `metadata_architecture.md` is canonical for identity resolution.**

---

## TIDAL → Beatport Flow

### Intake: `TidalSeedRow` / `TIDAL_SEED_COLUMNS`

Produced by `tidal-seed` command. One row per track in a TIDAL playlist.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `tidal_playlist_id` | str | TIDAL playlist | |
| `tidal_track_id` | str | TIDAL track ID | |
| `tidal_url` | str | Constructed | `https://tidal.com/browse/track/{id}` |
| `title` | str | TIDAL attributes | |
| `artist` | str | TIDAL relationships | Comma-separated if multiple |
| `isrc` | str? | TIDAL attributes | May be absent |

### Output: `TidalBeatportMergedRow` / `TIDAL_BEATPORT_MERGED_COLUMNS`

Produced by `beatport-enrich` command. Extends seed row with Beatport enrichment.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `tidal_playlist_id` | str | Passthrough | |
| `tidal_track_id` | str | Passthrough | |
| `tidal_url` | str | Passthrough | |
| `title` | str | Passthrough | |
| `artist` | str | Passthrough | |
| `isrc` | str? | Passthrough | |
| `beatport_track_id` | str? | Beatport | |
| `beatport_release_id` | str? | Beatport | |
| `beatport_url` | str? | Beatport | |
| `beatport_bpm` | str? | Beatport | Serialized as string |
| `beatport_key` | str? | Beatport | e.g. `"F# min"` |
| `beatport_genre` | str? | Beatport | |
| `beatport_subgenre` | str? | Beatport | |
| `beatport_label` | str? | Beatport | |
| `beatport_catalog_number` | str? | Beatport | |
| `beatport_upc` | str? | Beatport release | |
| `beatport_release_date` | str? | Beatport | ISO date string |
| `match_method` | str | Enricher | `"isrc"`, `"title_artist_fallback"`, `"no_match"` |
| `match_confidence` | float | Enricher | Serialized from `MatchConfidence` via `CONFIDENCE_NUMERIC` |
| `last_synced_at` | str? | Enricher | ISO 8601 UTC timestamp |

---

## Beatport → TIDAL Flow

### Intake: `BeatportSeedRow` / `BEATPORT_SEED_COLUMNS`

Produced by `beatport-seed` command. One row per track in the authenticated Beatport library.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `beatport_track_id` | str | Beatport | |
| `beatport_release_id` | str? | Beatport | |
| `beatport_url` | str | Beatport | |
| `title` | str | Beatport | |
| `artist` | str | Beatport | Comma-separated |
| `isrc` | str? | Beatport | May be absent |
| `beatport_bpm` | str? | Beatport | |
| `beatport_key` | str? | Beatport | |
| `beatport_genre` | str? | Beatport | |
| `beatport_subgenre` | str? | Beatport | |
| `beatport_label` | str? | Beatport | |
| `beatport_catalog_number` | str? | Beatport | |
| `beatport_upc` | str? | Beatport | |
| `beatport_release_date` | str? | Beatport | |

### Output: `BeatportTidalMergedRow` / `BEATPORT_TIDAL_MERGED_COLUMNS`

Produced by `tidal-enrich` command. Extends seed row with TIDAL enrichment.

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `beatport_track_id` | str | Passthrough | |
| `beatport_release_id` | str? | Passthrough | |
| `beatport_url` | str | Passthrough | |
| `title` | str | Passthrough | |
| `artist` | str | Passthrough | |
| `isrc` | str? | Passthrough | |
| `beatport_bpm` | str? | Passthrough | |
| `beatport_key` | str? | Passthrough | |
| `beatport_genre` | str? | Passthrough | |
| `beatport_subgenre` | str? | Passthrough | |
| `beatport_label` | str? | Passthrough | |
| `beatport_catalog_number` | str? | Passthrough | |
| `beatport_upc` | str? | Passthrough | |
| `beatport_release_date` | str? | Passthrough | |
| `tidal_track_id` | str? | TIDAL | |
| `tidal_url` | str? | TIDAL | |
| `tidal_title` | str? | TIDAL | |
| `tidal_artist` | str? | TIDAL | |
| `match_method` | str | Enricher | `"isrc"`, `"title_artist_fallback"`, `"no_match"` |
| `match_confidence` | float | Enricher | Serialized from `MatchConfidence` via `CONFIDENCE_NUMERIC` |
| `last_synced_at` | str? | Enricher | ISO 8601 UTC timestamp |

---

## Schema Stability Rules

1. `TIDAL_SEED_COLUMNS`, `TIDAL_BEATPORT_MERGED_COLUMNS`, `BEATPORT_SEED_COLUMNS`, `BEATPORT_TIDAL_MERGED_COLUMNS` are frozen tuples. Changes require contract doc update in the same PR.
2. Column order is stable. Downstream consumers depend on it.
3. `match_confidence` in CSV is always a float (serialized from enum). The dataclass field is `MatchConfidence` enum; serialization happens at write time.
4. Dropped-provider columns (Apple Music, Spotify, etc.) must not appear in these schemas.

---

## Field Mapping: CSV → Identity Service → `track_identity`

| CSV Column | `resolve_or_create_identity()` metadata key | `track_identity` column |
|------------|---------------------------------------------|------------------------|
| `isrc` | `isrc` | `isrc` |
| `beatport_track_id` | `beatport_id` | `beatport_id` |
| `tidal_track_id` | `tidal_id` | `tidal_id` |
| `title` | `title` / `canonical_title` | `canonical_title` |
| `artist` | `artist` / `canonical_artist` | `canonical_artist` |
| `beatport_bpm` | `bpm` / `canonical_bpm` | `canonical_bpm` |
| `beatport_key` | `key` / `canonical_key` | `canonical_key` |
| `beatport_genre` | `genre` / `canonical_genre` | `canonical_genre` |
| `beatport_subgenre` | `sub_genre` / `canonical_sub_genre` | `canonical_sub_genre` |
| `beatport_label` | `label` / `canonical_label` | `canonical_label` |
| `beatport_catalog_number` | `catalog_number` / `canonical_catalog_number` | `canonical_catalog_number` |
| `beatport_release_date` | `release_date` / `canonical_release_date` | `canonical_release_date` |
| `match_confidence` | *(not passed to identity service directly)* | *(stored in asset_link.confidence)* |

**Note:** The batch CSV path does not currently write to `track_identity` via `identity_service`. The field mapping above describes the intended bridge interface (Phase O4).
