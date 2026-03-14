-- Migration 0010: DJ pipeline tables (authoritative DJ layer)
--
-- Supersedes the table stubs introduced in 0009 with a richer, production-ready
-- schema that includes zone tracking, reconciliation columns, and a full
-- reconcile_log. All statements use IF NOT EXISTS so this migration is safe
-- to replay after a partial failure or if 0009 was previously applied.
--
-- Tables created:
--   mp3_asset, dj_admission, dj_track_id_map,
--   dj_playlist, dj_playlist_track, dj_export_state, reconcile_log

PRAGMA foreign_keys = ON;

BEGIN;

-- ---------------------------------------------------------------------------
-- mp3_asset
-- Derivative MP3 asset; may exist without a canonical identity_id for legacy
-- imports. content_sha256 is the primary integrity anchor.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mp3_asset (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  identity_id      INTEGER REFERENCES track_identity(id),
  asset_id         INTEGER REFERENCES asset_file(id),
  path             TEXT    NOT NULL UNIQUE,
  content_sha256   TEXT,
  size_bytes       INTEGER,
  bitrate          INTEGER,
  sample_rate      INTEGER,
  duration_s       REAL,
  profile          TEXT    NOT NULL DEFAULT 'standard',
  status           TEXT    NOT NULL DEFAULT 'unverified'
                     CHECK(status IN ('unverified','verified','missing','superseded')),
  source           TEXT    NOT NULL DEFAULT 'unknown',
  zone             TEXT,
  transcoded_at    TEXT,
  reconciled_at    TEXT,
  lexicon_track_id INTEGER,
  created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
  updated_at       TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mp3_asset_identity ON mp3_asset(identity_id);
CREATE INDEX IF NOT EXISTS idx_mp3_asset_zone     ON mp3_asset(zone);
CREATE INDEX IF NOT EXISTS idx_mp3_asset_lexicon  ON mp3_asset(lexicon_track_id);

-- ---------------------------------------------------------------------------
-- dj_admission
-- One row per track_identity admitted to the live DJ library.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dj_admission (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  identity_id  INTEGER UNIQUE REFERENCES track_identity(id),
  mp3_asset_id INTEGER REFERENCES mp3_asset(id),
  status       TEXT    NOT NULL DEFAULT 'pending'
                 CHECK(status IN ('pending','admitted','rejected','needs_review')),
  source       TEXT    NOT NULL DEFAULT 'unknown',
  notes        TEXT,
  admitted_at  TEXT,
  created_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dj_admission_identity ON dj_admission(identity_id);

-- ---------------------------------------------------------------------------
-- dj_track_id_map
-- Stable Rekordbox TrackID assignment; decoupled from admission so IDs
-- survive re-admission or asset swaps.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dj_track_id_map (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  dj_admission_id    INTEGER UNIQUE REFERENCES dj_admission(id),
  rekordbox_track_id INTEGER NOT NULL UNIQUE,
  assigned_at        TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- dj_playlist / dj_playlist_track
-- Hierarchical playlist tree mirroring the Rekordbox folder/playlist layout.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dj_playlist (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  name                TEXT    NOT NULL,
  parent_id           INTEGER REFERENCES dj_playlist(id),
  lexicon_playlist_id INTEGER,
  sort_key            TEXT,
  playlist_type       TEXT    DEFAULT 'standard',
  created_at          TEXT    DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(name, parent_id)
);

CREATE TABLE IF NOT EXISTS dj_playlist_track (
  playlist_id     INTEGER NOT NULL REFERENCES dj_playlist(id),
  dj_admission_id INTEGER NOT NULL REFERENCES dj_admission(id),
  ordinal         INTEGER NOT NULL,
  PRIMARY KEY (playlist_id, dj_admission_id)
);

-- ---------------------------------------------------------------------------
-- dj_export_state
-- One row per XML/NML/M3U emit so diffs can be computed on the next export.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dj_export_state (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  kind          TEXT    NOT NULL,
  output_path   TEXT    NOT NULL,
  manifest_hash TEXT,
  scope_json    TEXT,
  emitted_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- reconcile_log
-- Append-only log of every reconciliation decision (file->identity linking,
-- confidence scoring, manual overrides).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconcile_log (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id           TEXT    NOT NULL,
  event_time       TEXT    DEFAULT CURRENT_TIMESTAMP,
  source           TEXT    NOT NULL,
  action           TEXT    NOT NULL,
  confidence       TEXT,
  mp3_path         TEXT,
  identity_id      INTEGER,
  lexicon_track_id INTEGER,
  details_json     TEXT
);

CREATE INDEX IF NOT EXISTS idx_reconcile_log_run      ON reconcile_log(run_id);
CREATE INDEX IF NOT EXISTS idx_reconcile_log_identity ON reconcile_log(identity_id);

COMMIT;
