-- Migration 0008: add dj_set_role and dj_subrole to files table
ALTER TABLE files ADD COLUMN IF NOT EXISTS dj_set_role TEXT;
ALTER TABLE files ADD COLUMN IF NOT EXISTS dj_subrole  TEXT;
CREATE INDEX IF NOT EXISTS idx_dj_set_role ON files(dj_set_role);
CREATE INDEX IF NOT EXISTS idx_dj_subrole  ON files(dj_subrole);
