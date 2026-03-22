ALTER TABLE track_identity
  ADD CONSTRAINT chk_ingestion_confidence
  CHECK (ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy'));

ALTER TABLE track_identity
  ADD CONSTRAINT chk_ingestion_method
  CHECK (ingestion_method IN (
      'provider_api','isrc_lookup','fingerprint_match',
      'fuzzy_text_match','picard_tag','manual','migration',
      'multi_provider_reconcile'
  ));
