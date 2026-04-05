ALTER TABLE asset_file ADD COLUMN status TEXT NOT NULL DEFAULT 'ok'
  CHECK (status IN ('pending','ok','blocked'));

ALTER TABLE asset_file ADD COLUMN blocked_reason TEXT;

CREATE TABLE IF NOT EXISTS cohort (
    id              INTEGER PRIMARY KEY,
    source_url      TEXT,
    source_kind     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','complete','blocked')),
    blocked_reason  TEXT,
    created_at      TEXT NOT NULL,
    completed_at    TEXT,
    flags           TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS cohort_file (
    id              INTEGER PRIMARY KEY,
    cohort_id       INTEGER NOT NULL REFERENCES cohort(id),
    asset_file_id   INTEGER REFERENCES asset_file(id),
    source_path     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','ok','blocked')),
    blocked_reason  TEXT,
    blocked_stage   TEXT,
    created_at      TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
  VALUES ('v3', 18, '0018_blocked_cohort_state.sql');
