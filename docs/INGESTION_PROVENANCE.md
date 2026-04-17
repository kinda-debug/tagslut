# Ingestion provenance (v3)

`track_identity` rows must include:

- `ingested_at` (UTC ISO 8601)
- `ingestion_method` (controlled vocabulary)
- `ingestion_source` (evidence string)
- `ingestion_confidence` (`verified` | `corroborated` | `high` | `uncertain` | `legacy`)

## `ingestion_method` controlled vocabulary

- `provider_api`
- `isrc_lookup`
- `fingerprint_match`
- `fuzzy_text_match`
- `picard_tag`
- `manual`
- `migration`
- `multi_provider_reconcile`
- `spotify_intake`
- `spotiflac_import`
- `mp3_reconcile`
- `mp3_consolidation`

## Lexicon evidence

Lexicon imports do not make Lexicon the cross-format identity owner. They attach
Lexicon evidence to existing identities and MP3 assets.

`tagslut lexicon import` reads Lexicon `main.db` directly or from a backup ZIP
containing `main.db`. It preserves snapshot evidence in
`track_identity.canonical_payload_json` using these keys:

- `lexicon_track_id`
- `lexicon_location`
- `lexicon_location_unique`
- `lexicon_fingerprint`
- `lexicon_import_source`
- `lexicon_source_payload`

Path matching prefers normalized `Track.locationUnique`, then normalized
`Track.location`. File tags and reports are treated as mirrors or operational
evidence, not as the primary Lexicon source of truth.
