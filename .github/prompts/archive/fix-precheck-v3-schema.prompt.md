# Fix pre_download_check.py — migrate load_db_rows to v3 schema

Agent instructions: AGENT.md, CLAUDE.md

Read first:
  tools/review/pre_download_check.py   — full file, understand all functions
  tagslut/storage/v3/schema.py         — v3 table definitions
  docs/DB_V3_SCHEMA.md                 — ownership model

---

## Context

`pre_download_check.py` has two DB lookup phases:

Phase 1 — `load_downloaded_track_ids()` (~line 200)
  Already queries v3 tables (asset_file JOIN asset_link JOIN track_identity)
  with a graceful sqlite3.OperationalError fallback for old DBs.
  DO NOT touch this function — it is correct.

Phase 2 — `load_db_rows()` (~line 270)
  Queries the legacy flat `files` table which does not exist in the v3
  fresh DB. This is the only function that needs updating.

---

## Task

Update `load_db_rows()` to query v3 tables while maintaining full
backward compatibility with old DBs that still have the `files` table.

### The DbRow dataclass (do not change)

  @dataclass
  class DbRow:
      path: str
      isrc: str
      beatport_id: str
      tidal_id: str
      title: str
      artist: str
      album: str
      download_source: str
      quality_rank: int | None

### Column mapping — files table → v3 tables

  files.path              → asset_file.path
  files.canonical_isrc    → track_identity.isrc
  files.beatport_id       → track_identity.beatport_id
  files.tidal_id          → track_identity.tidal_id
  files.canonical_title   → track_identity.canonical_title
  files.canonical_artist  → track_identity.canonical_artist
  files.canonical_album   → track_identity.canonical_album
  files.bit_depth         → asset_file.bit_depth
  files.sample_rate       → asset_file.sample_rate
  files.bitrate           → asset_file.bitrate
  files.metadata_json     → not needed (v3 has dedicated columns)
  files.download_source   → asset_file.download_source
  files.quality_rank      → not a stored column — compute via infer_quality_rank()

### The v3 JOIN

  SELECT
      af.path,
      ti.isrc                 AS canonical_isrc,
      ti.beatport_id,
      ti.tidal_id,
      ti.canonical_title,
      ti.canonical_artist,
      ti.canonical_album,
      af.bit_depth,
      af.sample_rate,
      af.bitrate,
      af.download_source,
      NULL                    AS metadata_json,
      NULL                    AS quality_rank
  FROM asset_file af
  JOIN asset_link al ON al.asset_id = af.id AND al.active = 1
  JOIN track_identity ti
      ON ti.id = al.identity_id
      AND ti.merged_into_id IS NULL

### Implementation pattern

Replace the single `cur.execute(... FROM files ...)` with a try/except
that tries v3 first, falls back to `files` for legacy DBs:

  try:
      cur.execute(V3_QUERY)
  except sqlite3.OperationalError:
      try:
          cur.execute(LEGACY_FILES_QUERY)
      except sqlite3.OperationalError:
          conn.close()
          return by_isrc, by_beatport, by_tidal, by_exact3, by_exact2

This ensures:
- Fresh v3 DB: uses asset_file JOIN track_identity
- Legacy DB with files table: falls back to original query
- DB with neither: returns empty dicts gracefully

The rest of the function (row processing, DbRow construction, index building)
stays identical — the column names in the SELECT alias match the existing
r["canonical_isrc"], r["beatport_id"] etc. field reads.

---

## Verify

  python -c "
import sqlite3
from pathlib import Path
from tagslut.storage.v3.schema import create_schema_v3
from tools.review.pre_download_check import load_db_rows
import tempfile, os

# Test 1: fresh v3 DB — should not raise
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
    db_path = Path(f.name)
conn = sqlite3.connect(str(db_path))
create_schema_v3(conn)
conn.close()
result = load_db_rows(db_path)
assert len(result) == 5
print('PASS: fresh v3 DB returns 5 empty dicts')
os.unlink(db_path)

# Test 2: empty DB (no tables) — should not raise
with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
    db_path = Path(f.name)
result = load_db_rows(db_path)
assert len(result) == 5
print('PASS: empty DB returns 5 empty dicts')
os.unlink(db_path)
"

  # End-to-end test with real fresh DB:
  tools/get --enrich https://tidal.com/album/497862476/u

---

## Commit

  git add tools/review/pre_download_check.py
  git commit -m "fix(precheck): migrate load_db_rows Phase 2 query to v3 schema with legacy fallback"
  git push

## Constraints

- Touch only the `load_db_rows` function. No other changes.
- Do not change `load_downloaded_track_ids` — it is already v3-aware.
- Do not change the `DbRow` dataclass.
- Do not change any other function in the file.
- The fallback to the legacy `files` table must remain for existing DBs.
