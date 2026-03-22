-- Migration 0009: add mp3_asset and dj_* tables for explicit derivative and DJ layers
--
-- Phase 1 (additive only): introduces new tables with no behavior change to existing code.
-- Existing dj_pool_path / rekordbox_id columns on `files` are preserved for compatibility.
-- New authoritative DJ state should be written exclusively to these tables going forward.

-- Derivative MP3 assets, keyed to canonical identity and master asset.
CREATE TABLE IF NOT EXISTS mp3_asset (
  id              INTEGER PRIMARY KEY,
  identity_id     INTEGER NOT NULL,
  master_asset_id INTEGER NOT NULL,
  profile         TEXT    NOT NULL DEFAULT 'mp3_320_cbr',
  path            TEXT    NOT NULL UNIQUE,
  sha256          TEXT,
  bitrate         INTEGER,
  sample_rate     INTEGER,
  status          TEXT    NOT NULL DEFAULT 'ok',
  transcoded_at   TEXT,
  FOREIGN KEY(identity_id)     REFERENCES track_identity(id),
  FOREIGN KEY(master_asset_id) REFERENCES asset_file(id)
);

CREATE INDEX IF NOT EXISTS idx_mp3_asset_identity ON mp3_asset(identity_id);
CREATE INDEX IF NOT EXISTS idx_mp3_asset_path     ON mp3_asset(path);
CREATE INDEX IF NOT EXISTS idx_mp3_asset_status   ON mp3_asset(status);

-- DJ admission: one row per identity admitted to the DJ library.
CREATE TABLE IF NOT EXISTS dj_admission (
  id                     INTEGER PRIMARY KEY,
  identity_id            INTEGER NOT NULL UNIQUE,
  preferred_mp3_asset_id INTEGER NOT NULL,
  status                 TEXT    NOT NULL DEFAULT 'active',
  admitted_at            TEXT,
  notes_json             TEXT,
  FOREIGN KEY(identity_id)            REFERENCES track_identity(id),
  FOREIGN KEY(preferred_mp3_asset_id) REFERENCES mp3_asset(id)
);

CREATE INDEX IF NOT EXISTS idx_dj_admission_identity ON dj_admission(identity_id);
CREATE INDEX IF NOT EXISTS idx_dj_admission_status   ON dj_admission(status);

-- Stable Rekordbox TrackID mapping; separated so IDs survive admission updates.
CREATE TABLE IF NOT EXISTS dj_track_id_map (
  id                 INTEGER PRIMARY KEY,
  dj_admission_id    INTEGER NOT NULL UNIQUE,
  rekordbox_track_id INTEGER NOT NULL UNIQUE,
  assigned_at        TEXT,
  FOREIGN KEY(dj_admission_id) REFERENCES dj_admission(id)
);

-- Playlists and nested folders.
CREATE TABLE IF NOT EXISTS dj_playlist (
  id        INTEGER PRIMARY KEY,
  name      TEXT    NOT NULL,
  parent_id INTEGER,
  sort_key  TEXT,
  UNIQUE(name, parent_id),
  FOREIGN KEY(parent_id) REFERENCES dj_playlist(id)
);

-- Ordered playlist membership.
CREATE TABLE IF NOT EXISTS dj_playlist_track (
  playlist_id     INTEGER NOT NULL,
  dj_admission_id INTEGER NOT NULL,
  ordinal         INTEGER NOT NULL,
  PRIMARY KEY (playlist_id, dj_admission_id),
  FOREIGN KEY(playlist_id)     REFERENCES dj_playlist(id),
  FOREIGN KEY(dj_admission_id) REFERENCES dj_admission(id)
);

-- Export manifests for deterministic XML emit/patch tracking.
CREATE TABLE IF NOT EXISTS dj_export_state (
  id            INTEGER PRIMARY KEY,
  kind          TEXT NOT NULL,
  output_path   TEXT NOT NULL,
  manifest_hash TEXT,
  emitted_at    TEXT,
  details_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_dj_export_state_kind ON dj_export_state(kind);
