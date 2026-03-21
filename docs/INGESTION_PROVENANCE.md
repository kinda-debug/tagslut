# Ingestion Provenance Standard

<!-- Status: Active. Required reading before any clean-slate DB ingestion. -->
<!-- Created: 2026-03-21 -->

## The problem

Half the library is 70% trustworthy. That 30% margin of doubt is
not random — it is traceable to specific ingestion methods that
produced unverifiable identities. Without a structured provenance
record per track, there is no way to query "which tracks were matched
by Picard", "which tracks have a Beatport-confirmed ISRC", or
"which tracks were fuzzy-matched without provider verification".

The clean-slate DB must make provenance a first-class, queryable
property from day one. It cannot be reconstructed retroactively.

## Core principle

Every `track_identity` row must have an indelible record of:
1. When it entered the system (timestamp, not mutable)
2. How it was identified (method)
3. What the source of that identification was (provider + evidence)
4. How confident that identification is (tier, not a float)

This record must be written at ingestion time and never overwritten.
Enrichment can add to it. Nothing can remove it.


## The four provenance fields (required on every track_identity row)

### 1. `ingested_at` — ISO 8601 UTC timestamp, set once, never updated

The moment the row was first written to `track_identity`.
Distinct from `created_at` (which may be updated on merge) and
`enriched_at` (which records the last enrichment run).
This field must be set by the insert statement and never touched again.
Migrations must backfill it from `created_at` where null.

### 2. `ingestion_method` — controlled vocabulary, one of:

  `provider_api`        Track entered via a provider API call with a
                        confirmed provider ID (Beatport, TIDAL, etc).
                        This is the only method that produces full-trust
                        identities in the clean-slate build.

  `isrc_lookup`         Track entered via ISRC lookup against a provider
                        API. ISRC was present in file tags or a receipt
                        and was verified against the provider response.

  `fingerprint_match`   Track entered via acoustic fingerprint match
                        (AcoustID/Chromaprint). Confidence depends on
                        match score stored separately.

  `fuzzy_text_match`    Track entered via normalized text matching
                        (artist + title). Lowest trust. Must never be
                        used as the sole identification method in the
                        clean-slate build.

  `picard_tag`          Track entered from MusicBrainz Picard-written
                        tags. Legacy method. Must never appear in the
                        clean-slate DB. Any row with this method is
                        flagged as legacy-contaminated.

  `manual`              Track entered by explicit operator decision,
                        with a written note in `ingestion_note`.

  `migration`           Row created during a DB migration or backfill.
                        Confidence tier is inherited from the source
                        row's original method, or `uncertain` if unknown.

### 3. `ingestion_source` — free text, the specific evidence used

Examples:
  "beatport_api:track_id=12345678"
  "tidal_api:isrc=GBUM71505512"
  "acoustid:score=0.94:recording_id=abc-def"
  "beatport_receipt:order_id=ORD-2024-001"
  "manual:operator=georgeskhawam:note=verified against vinyl label"

This field is the audit trail. It must be specific enough that the
identification could be re-verified against the original source.

### 4. `ingestion_confidence` — four-tier controlled vocabulary:

  `verified`      Provider API returned this track with a matching
                  provider ID and ISRC. Two independent provider
                  signals agree. Highest trust.

  `high`          Single provider API match with confirmed provider ID.
                  No cross-verification, but the match was unambiguous.

  `uncertain`     Fuzzy match, fingerprint match below 0.90, or
                  text-only match. Usable but flagged for review.

  `legacy`        Picard tag, migration from old DB, or unknown origin.
                  Do not use for DJ export or canonical operations
                  without manual review.


## Schema migration required

The following columns must be added to `track_identity` before
any clean-slate ingestion begins:

```sql
ALTER TABLE track_identity ADD COLUMN ingested_at TEXT;
ALTER TABLE track_identity ADD COLUMN ingestion_method TEXT;
ALTER TABLE track_identity ADD COLUMN ingestion_source TEXT;
ALTER TABLE track_identity ADD COLUMN ingestion_confidence TEXT;

-- Backfill for any existing rows (legacy epoch only)
UPDATE track_identity
SET
  ingested_at = COALESCE(created_at, datetime('now')),
  ingestion_method = 'migration',
  ingestion_confidence = 'legacy'
WHERE ingested_at IS NULL;

-- Index for provenance queries
CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_confidence
  ON track_identity (ingestion_confidence);

CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_method
  ON track_identity (ingestion_method);

CREATE INDEX IF NOT EXISTS idx_track_identity_ingested_at
  ON track_identity (ingested_at);
```

This migration must be the first migration applied to the fresh DB,
before any ingestion runs. It must be a numbered migration file in
`supabase/migrations/` and must be committed before the DB is initialized.

## asset_link provenance fields (already exist, use them correctly)

`asset_link` already has `confidence` and `link_source`. These must
be populated consistently with `track_identity.ingestion_confidence`
and `ingestion_source` on every insert. They are not optional.

## Queries enabled by this standard

```sql
-- All tracks with uncertain or legacy provenance
SELECT ti.canonical_artist, ti.canonical_title, ti.ingestion_method,
       ti.ingestion_source, ti.ingestion_confidence
FROM track_identity ti
WHERE ti.ingestion_confidence IN ('uncertain', 'legacy')
ORDER BY ti.ingested_at;

-- Trust breakdown of the full library
SELECT ingestion_confidence, ingestion_method, COUNT(*) as n
FROM track_identity
GROUP BY ingestion_confidence, ingestion_method
ORDER BY n DESC;

-- Tracks that entered via provider API (full trust)
SELECT COUNT(*) FROM track_identity
WHERE ingestion_method = 'provider_api'
AND ingestion_confidence IN ('verified', 'high');

-- Tracks needing review before DJ export
SELECT ti.canonical_artist, ti.canonical_title, ti.ingested_at
FROM track_identity ti
JOIN asset_link al ON al.identity_id = ti.id
WHERE ti.ingestion_confidence IN ('uncertain', 'legacy')
AND al.active = 1;
```

## Enforcement in the intake pipeline

`tools/get-intake` must write these fields on every `track_identity`
insert. The insert must fail if `ingested_at` or `ingestion_method`
is NULL — these are NOT NULL constraints in the migration.

`tagslut/storage/v3/schema.py` must be updated to reflect the new
columns before any clean-slate DB is initialized.

## What this means for the existing library

Every track already in `music_v3.db` gets `ingestion_method = 'migration'`
and `ingestion_confidence = 'legacy'` via the backfill above.
This makes the 30% doubt margin explicit and queryable rather than
implicit and invisible. You can then run re-verification passes against
the provider APIs to upgrade rows from `legacy` to `high` or `verified`
where a match is confirmed — and those upgrades are also logged in
`provenance_event` with a timestamp.

