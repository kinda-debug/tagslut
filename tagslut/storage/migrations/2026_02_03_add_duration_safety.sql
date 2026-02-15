-- Duration-aware DJ safety fields
ALTER TABLE files ADD COLUMN is_dj_material INTEGER NOT NULL DEFAULT 0;
ALTER TABLE files ADD COLUMN duration_ref_ms INTEGER;
ALTER TABLE files ADD COLUMN duration_ref_source TEXT;
ALTER TABLE files ADD COLUMN duration_ref_track_id TEXT;
ALTER TABLE files ADD COLUMN duration_ref_updated_at TEXT;
ALTER TABLE files ADD COLUMN duration_measured_ms INTEGER;
ALTER TABLE files ADD COLUMN duration_measured_at TEXT;
ALTER TABLE files ADD COLUMN duration_delta_ms INTEGER;
ALTER TABLE files ADD COLUMN duration_status TEXT;
ALTER TABLE files ADD COLUMN duration_check_version TEXT;

CREATE TABLE IF NOT EXISTS track_duration_refs (
  ref_id TEXT PRIMARY KEY,
  ref_type TEXT NOT NULL,
  duration_ref_ms INTEGER NOT NULL,
  ref_source TEXT NOT NULL,
  ref_updated_at TEXT
);
