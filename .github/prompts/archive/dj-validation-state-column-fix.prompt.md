# Fix: dj_validation_state column name mismatch

**COMMIT ALL CHANGES BEFORE EXITING. If you do not commit, the work is lost.**

**CRITICAL**: Do not touch schema.py, any other migration files, or any file
not listed below. Targeted fix only.

---

## Problem

The live `dj_validation_state` table has column `validated_at` (from the CREATE TABLE
in migration 0014). The INSERT in `tagslut/storage/v3/dj_state.py` uses `created_at`
instead, causing `sqlite3.IntegrityError: NOT NULL constraint failed: dj_validation_state.validated_at`.

A manual `ALTER TABLE ... ADD COLUMN created_at` was run as a workaround and must be
cleaned up.

---

## Fix

### Step 1 — Fix the INSERT in dj_state.py

In `tagslut/storage/v3/dj_state.py`, find the INSERT into `dj_validation_state`.
Change `created_at` to `validated_at` in both the column list and the VALUES clause.
The value is already correct (`datetime.now(timezone.utc).isoformat()`).

### Step 2 — Remove the stale created_at column from the live DB

The FRESH DB at `$TAGSLUT_DB` (default: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`)
has a spurious `created_at` column added manually. SQLite does not support DROP COLUMN
on older versions, so recreate the table without it:

```sql
BEGIN;
CREATE TABLE dj_validation_state_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    validated_at TEXT NOT NULL,
    state_hash TEXT NOT NULL,
    issue_count INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    summary TEXT
);
INSERT INTO dj_validation_state_new (id, validated_at, state_hash, issue_count, passed, summary)
    SELECT id, validated_at, state_hash, issue_count, passed, summary
    FROM dj_validation_state;
DROP TABLE dj_validation_state;
ALTER TABLE dj_validation_state_new RENAME TO dj_validation_state;
CREATE INDEX IF NOT EXISTS idx_dj_validation_state_hash ON dj_validation_state(state_hash);
COMMIT;
```

Run this against `$TAGSLUT_DB`.

### Step 3 — Fix migration 0014 to match live schema

In `tagslut/storage/v3/migrations/0014_dj_validation_state.py`, change `created_at`
to `validated_at` in the CREATE TABLE DDL so future fresh DB initializations produce
the correct schema.

---

## Verification

```bash
sqlite3 "$TAGSLUT_DB" ".schema dj_validation_state"
# Must show validated_at, no created_at

tagslut dj validate
# Must complete without error and print state_hash
```

---

## Commit message

```
fix(dj): align dj_validation_state INSERT and migration to use validated_at column
```
