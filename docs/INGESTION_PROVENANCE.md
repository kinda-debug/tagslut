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

