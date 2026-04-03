ALTER TABLE track_identity ADD COLUMN tidal_bpm REAL;
ALTER TABLE track_identity ADD COLUMN tidal_key TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_key_scale TEXT;
ALTER TABLE track_identity ADD COLUMN tidal_camelot TEXT;
ALTER TABLE track_identity ADD COLUMN replay_gain_track REAL;
ALTER TABLE track_identity ADD COLUMN replay_gain_album REAL;
ALTER TABLE track_identity ADD COLUMN tidal_dj_ready INTEGER;
ALTER TABLE track_identity ADD COLUMN tidal_stem_ready INTEGER;
INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
  VALUES ('v3', 16, '0016_tidal_audio_fields.sql');
