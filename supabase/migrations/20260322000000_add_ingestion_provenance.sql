-- Migration: Add ingestion provenance columns to track_identity
-- Matches SQLite migration 0012_ingestion_provenance.py

-- 1. Add columns
ALTER TABLE track_identity ADD COLUMN IF NOT EXISTS ingested_at TEXT;
ALTER TABLE track_identity ADD COLUMN IF NOT EXISTS ingestion_method TEXT;
ALTER TABLE track_identity ADD COLUMN IF NOT EXISTS ingestion_source TEXT;
ALTER TABLE track_identity ADD COLUMN IF NOT EXISTS ingestion_confidence TEXT;

-- 2. Backfill existing rows
UPDATE track_identity
SET
    ingested_at       = COALESCE(ingested_at, created_at, NOW()::TEXT),
    ingestion_method  = COALESCE(ingestion_method, 'migration'),
    ingestion_source  = COALESCE(ingestion_source, 'legacy_backfill'),
    ingestion_confidence = COALESCE(ingestion_confidence, 'legacy')
WHERE ingested_at IS NULL
   OR ingestion_method IS NULL
   OR ingestion_source IS NULL
   OR ingestion_confidence IS NULL;

-- 3. Enforce NOT NULL after backfill
ALTER TABLE track_identity ALTER COLUMN ingested_at SET NOT NULL;
ALTER TABLE track_identity ALTER COLUMN ingestion_method SET NOT NULL;
ALTER TABLE track_identity ALTER COLUMN ingestion_source SET NOT NULL;
ALTER TABLE track_identity ALTER COLUMN ingestion_confidence SET NOT NULL;

-- 4. Indexes
CREATE INDEX IF NOT EXISTS idx_track_identity_ingested_at ON track_identity(ingested_at);
CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_method ON track_identity(ingestion_method);
CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_confidence ON track_identity(ingestion_confidence);
