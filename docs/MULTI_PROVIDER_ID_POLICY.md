# Multi-Provider ID Policy

<!-- Status: Active. Required reading before any identity resolution work. -->
<!-- Created: 2026-03-21 -->
<!-- Supersedes: implicit assumptions in INGESTION_PROVENANCE.md §confidence tiers -->

---

## The core rule

All provider IDs (`spotify_id`, `qobuz_id`, `beatport_id`, `tidal_id`,
`apple_music_id`, `deezer_id`, `traxsource_id`) are preserved on every
`track_identity` row if they do not conflict with the ISRC.

Agreement across multiple provider IDs pointing to the same ISRC is
**positive confirmation** — it raises confidence.

Conflict between a provider ID and the ISRC is a **provenance failure**
— it must be flagged, not silently resolved.

---

## Confidence tier revision

This supersedes the four-tier model in `INGESTION_PROVENANCE.md`.
The correct five-tier model is:

| Tier | Definition |
|---|---|
| `verified` | Two or more independent provider APIs confirmed the same ISRC at ingest time (active cross-check, not just stored IDs agreeing). |
| `corroborated` | Multiple stored provider IDs are present and all agree on the ISRC. No active cross-check was run, but the convergence is meaningful evidence. |
| `high` | Single provider API match with confirmed provider ID. No cross-verification. |
| `uncertain` | Fuzzy match, fingerprint below 0.90, or text-only match. |
| `legacy` | Picard tag, unknown origin, or migration from old DB without verification. |

`corroborated` is the key addition. It is the correct tier for older files
that have been matched by multiple providers over time and where all IDs agree.


---

## Three ingestion tracks

### Track A — Clean-slate (new files from provider APIs)

Applies to: files downloaded via `tools/get --enrich <url>` from Beatport or TIDAL.

Processing:
1. Provider API returns ISRC + provider ID at download time
2. `ingestion_method = 'provider_api'`
3. `ingestion_source = 'beatport_api:track_id=X'` or `'tidal_api:isrc=Y'`
4. If both providers agree on ISRC → `ingestion_confidence = 'verified'`
5. If single provider only → `ingestion_confidence = 'high'`
6. All other provider IDs left NULL — populated later by enrichment passes

### Track S — Spotify intake (Spotify-origin acquisition with provider fallback)

Applies to: files downloaded from Spotify track/album/playlist URLs through
`tools/get`, `tagslut intake url`, or `tools/get-intake`.

Processing:
1. Expand Spotify track metadata before precheck so duplicate gating still happens on a per-track basis
2. Acquire audio through the Spotify intake adapter with service order `qobuz -> tidal -> amazon`
3. Preserve the original Spotify URL plus the winning service/provider track ID in the acquisition manifest
4. `ingestion_method = 'spotify_intake'`
5. `ingestion_source = 'spotiflac:<spotify_url>|service:<winning_service>'`
6. `ingestion_confidence = 'high'` when ISRC is present, otherwise `uncertain`
7. Preserve `spotify_id` plus the winning provider ID (`qobuz_id` or `tidal_id`) when available

### Track B — Legacy (older files with accumulated cross-provider IDs)

Applies to: files that existed before the clean-slate build and have been
matched by multiple providers over time (Spotify match, Qobuz ID, etc.).

Operator note:
- There is no dedicated `tagslut intake legacy` command.
- Track B is an internal provenance classification applied when pre-existing
  files are registered from disk and already carry provider IDs in tags or
  metadata.
- For an unregistered root, the operator surface is
  `poetry run tagslut index register <root> --db <V3_DB> --source legacy --execute`
  (or `--source relink` after a DB relink). When provider IDs are present,
  v3 registration classifies the row as `ingestion_method='multi_provider_reconcile'`.
- `python -m tagslut intake process-root ...` is follow-on processing for an
  existing root; it does not create Track B rows by itself.

Processing:
1. Collect all provider IDs present for the file
2. Resolve ISRC from the most trusted available source (Beatport > TIDAL > ISRC tag)
3. Check every non-null provider ID against the resolved ISRC:
   - If ALL agree → `ingestion_confidence = 'corroborated'`
   - If ANY conflict → `ingestion_confidence = 'uncertain'`, flag the conflict
   - If only one provider ID present → `ingestion_confidence = 'high'`
4. `ingestion_method = 'multi_provider_reconcile'`
5. `ingestion_source` lists all provider IDs used:
   `'multi:beatport_id=X,spotify_id=Y,tidal_id=Z,isrc=ABC'`
6. Conflicting IDs are NOT discarded — they are preserved in the row with
   a conflict note in `canonical_payload_json` under `provider_id_conflicts`

### What "conflict" means

A conflict is: provider ID X resolves (via API lookup) to ISRC Y, but the
ISRC on the row is Z. This is not the same as a missing ID (NULL is fine).

A conflict is NOT: two provider IDs that both resolve to the same ISRC
via different paths. That is corroboration.


---

## Conflict handling

Conflicts are preserved, not resolved. The row keeps both the canonical ISRC
and the conflicting provider ID. The conflict is recorded in
`canonical_payload_json`:

```json
{
  "provider_id_conflicts": [
    {
      "provider": "spotify_id",
      "stored_value": "4abc123",
      "resolved_isrc": "GBUM71505512",
      "canonical_isrc": "USQX91501234",
      "detected_at": "2026-03-21T14:00:00Z"
    }
  ]
}
```

A track with any conflict entry must have `ingestion_confidence = 'uncertain'`
regardless of how many other IDs corroborate the canonical ISRC.

Resolution requires operator review. The operator either:
- Confirms the canonical ISRC is correct and NULLs the conflicting provider ID
- Determines the conflicting provider ID pointed to a different track entirely
  and corrects the identity

After resolution, the conflict entry is moved to `provider_id_conflicts_resolved`
in the same JSON field, with a `resolved_at` timestamp and `resolution` note.

---

## Queries enabled by this policy

```sql
-- All corroborated tracks (multiple providers agree)
SELECT canonical_artist, canonical_title, ingestion_source
FROM track_identity
WHERE ingestion_confidence = 'corroborated'
ORDER BY canonical_artist;

-- All tracks with provider ID conflicts requiring review
SELECT canonical_artist, canonical_title,
       json_extract(canonical_payload_json, '$.provider_id_conflicts') AS conflicts
FROM track_identity
WHERE ingestion_confidence = 'uncertain'
  AND json_extract(canonical_payload_json, '$.provider_id_conflicts') IS NOT NULL;

-- Provider ID coverage across library
SELECT
  COUNT(CASE WHEN spotify_id IS NOT NULL THEN 1 END)    AS has_spotify,
  COUNT(CASE WHEN qobuz_id IS NOT NULL THEN 1 END)      AS has_qobuz,
  COUNT(CASE WHEN beatport_id IS NOT NULL THEN 1 END)   AS has_beatport,
  COUNT(CASE WHEN tidal_id IS NOT NULL THEN 1 END)      AS has_tidal,
  COUNT(CASE WHEN apple_music_id IS NOT NULL THEN 1 END) AS has_apple,
  COUNT(*) AS total
FROM track_identity
WHERE merged_into_id IS NULL;

-- Tracks where corroboration could be upgraded to verified
-- (have both beatport_id and tidal_id, confidence not yet verified)
SELECT canonical_artist, canonical_title, beatport_id, tidal_id, isrc
FROM track_identity
WHERE beatport_id IS NOT NULL
  AND tidal_id IS NOT NULL
  AND ingestion_confidence != 'verified'
  AND merged_into_id IS NULL;
```

---

## Schema implication

`ingestion_confidence` CHECK constraint must be updated to allow five values:

```sql
CHECK (ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy'))
```

`ingestion_method` must include both `'multi_provider_reconcile'` and
`'spotify_intake'` in its controlled vocabulary.

This requires migration 0013 (or whichever is next after 0012).

---

## Relationship to INGESTION_PROVENANCE.md

`INGESTION_PROVENANCE.md` defines the per-row fields and the base vocabulary.
This document defines the multi-provider reconciliation policy and the
`corroborated` tier that extends it. Both documents are required reading
before any identity resolution work.

`INGESTION_PROVENANCE.md` §confidence tiers should reference this document
for the full five-tier definition.
