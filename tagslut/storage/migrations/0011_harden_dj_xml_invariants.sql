-- Migration 0011: Harden DJ XML invariants (validation gate + immutable TrackID map)
--
-- Adds the dj_validation_state table used by `tagslut dj validate` and enforces
-- strict invariants for dj_track_id_map and dj_export_state via triggers.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS dj_validation_state (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  validated_at TEXT    NOT NULL,
  state_hash   TEXT    NOT NULL,
  issue_count  INTEGER NOT NULL,
  passed       INTEGER NOT NULL CHECK(passed IN (0,1)),
  summary      TEXT
);

CREATE INDEX IF NOT EXISTS idx_dj_validation_state_hash ON dj_validation_state(state_hash);

CREATE TRIGGER IF NOT EXISTS trg_dj_track_id_map_no_null
BEFORE INSERT ON dj_track_id_map
WHEN NEW.dj_admission_id IS NULL OR NEW.rekordbox_track_id IS NULL
BEGIN
  SELECT RAISE(ABORT, 'dj_track_id_map requires dj_admission_id and rekordbox_track_id');
END;

CREATE TRIGGER IF NOT EXISTS trg_dj_track_id_map_immutable
BEFORE UPDATE ON dj_track_id_map
BEGIN
  SELECT RAISE(ABORT, 'dj_track_id_map rows are immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_dj_export_state_require_manifest
BEFORE INSERT ON dj_export_state
WHEN NEW.manifest_hash IS NULL OR NEW.scope_json IS NULL
BEGIN
  SELECT RAISE(ABORT, 'dj_export_state requires manifest_hash and scope_json');
END;

COMMIT;

