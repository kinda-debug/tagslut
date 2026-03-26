-- Migration 0014: DJ validation state gate table
--
-- Provides a durable "dj validate" gate record keyed by the current dj state hash.
-- This table is intentionally minimal; higher-level reporting remains in the CLI output.

CREATE TABLE IF NOT EXISTS dj_validation_state (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  state_hash TEXT NOT NULL,
  passed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

