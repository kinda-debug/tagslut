# Fix remaining test fixture — test_plan_backfill_identity_conflicts_v3.py

Agent instructions: AGENT.md, CLAUDE.md

Read first:
  tests/conftest.py          — PROV_COLS, PROV_VALS already defined
  tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py  — the failing test

---

## Problem

One test fixture was missed in migration 0012. The `_fixture_db` helper at
~line 54 inserts into `track_identity` without provenance columns:

  INSERT INTO track_identity (identity_key, isrc, artist_norm, title_norm,
      duration_ref_ms) VALUES (?, ?, ?, ?, ?)

After migration 0012 added the enforcement trigger, this fails with:
  sqlite3.IntegrityError: track_identity.ingested_at is required

## Fix

Import or inline PROV_COLS and PROV_VALS from tests/conftest.py.
If import causes path issues, inline:
  _PROV_COLS = ", ingested_at, ingestion_method, ingestion_source, ingestion_confidence"
  _PROV_VALS = ", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'"

Update the INSERT to append provenance to both the column list and
the VALUES tuple. Update all four rows in the executemany call to
include the four provenance values.

## Verify

  poetry run pytest tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py -v

Should show 1 passed.

## Commit

  git add tests/storage/v3/test_plan_backfill_identity_conflicts_v3.py
  git commit -m "fix(tests): add provenance fields to plan_backfill_identity_conflicts fixture"
  git push

## Constraints

Touch only the one INSERT statement and its executemany data tuples.
No other changes.
