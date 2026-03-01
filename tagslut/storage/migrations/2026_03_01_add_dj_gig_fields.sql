-- DJ pool output tracking columns
-- Added as part of the tagslut gig build workflow (#100).
-- These columns are also added automatically by init_db() via _add_missing_columns,
-- so this migration is safe to apply to any database state.

ALTER TABLE files ADD COLUMN IF NOT EXISTS dj_pool_path TEXT;
ALTER TABLE files ADD COLUMN IF NOT EXISTS quality_rank INTEGER;
ALTER TABLE files ADD COLUMN IF NOT EXISTS rekordbox_id INTEGER;
ALTER TABLE files ADD COLUMN IF NOT EXISTS last_exported_usb TEXT;

CREATE INDEX IF NOT EXISTS idx_quality_rank ON files(quality_rank);
CREATE INDEX IF NOT EXISTS idx_dj_pool_path ON files(dj_pool_path);
CREATE INDEX IF NOT EXISTS idx_last_exported_usb ON files(last_exported_usb);

-- Gig set tables
CREATE TABLE IF NOT EXISTS gig_sets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filter_expr TEXT,
    usb_path TEXT,
    manifest_path TEXT,
    track_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    exported_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_gig_sets_name ON gig_sets(name);
CREATE INDEX IF NOT EXISTS idx_gig_sets_exported_at ON gig_sets(exported_at);

CREATE TABLE IF NOT EXISTS gig_set_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gig_set_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    mp3_path TEXT,
    usb_dest_path TEXT,
    transcoded_at TEXT,
    exported_at TEXT,
    rekordbox_id INTEGER,
    FOREIGN KEY(gig_set_id) REFERENCES gig_sets(id)
);

CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_set ON gig_set_tracks(gig_set_id);
CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_file ON gig_set_tracks(file_path);
