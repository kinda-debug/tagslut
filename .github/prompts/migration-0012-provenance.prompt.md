You are an expert Python/SQLite engineer working in the tagslut repository.

Goal:
Complete migration 0012 — the ingestion provenance columns on `track_identity` are
partially implemented. The v3 schema path (`create_schema_v3`) is complete but the
legacy `init_db` path, several test fixtures, CHECK constraints, and documentation
are not yet updated. This prompt closes every remaining gap.

═══════════════════════════════════════════════════════
CONTEXT: Read these first, in order
═══════════════════════════════════════════════════════

Agent instructions:
  AGENT.md
  CLAUDE.md
  docs/PROJECT_DIRECTIVES.md

Spec documents (required reading — do not skip):
  docs/INGESTION_PROVENANCE.md
  docs/MULTI_PROVIDER_ID_POLICY.md

Already-implemented artifacts (read to understand current state):
  tagslut/storage/v3/schema.py                    — columns + trigger DONE
  tagslut/storage/v3/migrations/0012_ingestion_provenance.py  — migration DONE
  tagslut/storage/v3/dual_write.py                — provenance params DONE
  tagslut/storage/v3/identity_service.py           — _identity_value_map DONE
  supabase/migrations/20260322000000_add_ingestion_provenance.sql — migration DONE
  tests/conftest.py                                — PROV_DEFAULTS helper DONE

Tests and fixtures requiring updates:
  tests/e2e/test_dj_pipeline.py
  tests/metadata/test_track_db_sync.py
  tests/test_verify_v3_migration.py
  tests/test_migration_report_v2_to_v3.py

Schema documentation:
  docs/DB_V3_SCHEMA.md

═══════════════════════════════════════════════════════
OPERATING RULES
═══════════════════════════════════════════════════════

- Follow AGENT.md and CLAUDE.md in all decisions.
- Minimal, reversible patches only. No refactors outside scope.
- Plan before editing: output a verification block before touching any file.
- Commit after each logical step with a conventional message.
- Do not touch database files directly. Do not write to any volume.
- Targeted pytest only: poetry run pytest tests/<specific_file> -v
- Do not run the full test suite unless explicitly stated.

═══════════════════════════════════════════════════════
WHAT IS ALREADY DONE (do not redo)
═══════════════════════════════════════════════════════

1. schema.py — `create_schema_v3` includes the four columns as NOT NULL
   in the CREATE TABLE statement, plus the enforcement trigger
   `trg_track_identity_provenance_required`, plus three provenance indexes.
   V3_SCHEMA_VERSION = 12.

2. 0012_ingestion_provenance.py — idempotent ALTERs, backfill, indexes,
   trigger creation, schema_migrations record. Fully functional.

3. dual_write.py — `upsert_track_identity` accepts optional provenance
   kwargs. Falls back to sensible defaults via `_column_exists` guard.
   ON CONFLICT preserves provenance (does not overwrite on upsert).

4. identity_service.py — `_identity_value_map` reads provenance from
   the `provenance` dict and populates all four fields.

5. Postgres migration — columns added, backfilled, set NOT NULL, indexed.

6. conftest.py — `PROV_DEFAULTS`, `PROV_COLS`, `PROV_VALS` constants exist.

═══════════════════════════════════════════════════════
WHAT REMAINS (your tasks — execute in strict order)
═══════════════════════════════════════════════════════

── Task 1: Update _ensure_v3_schema in tagslut/storage/schema.py ──────────────

PROBLEM:
  `_ensure_v3_schema()` creates `track_identity` WITHOUT provenance columns
  and WITHOUT the enforcement trigger. Any code path going through `init_db`
  gets a table that silently accepts inserts missing provenance.

FIX:
  1. Add the four provenance columns to the `_add_missing_columns` call
     for `V3_TRACK_IDENTITY_TABLE`:
       "ingested_at": "TEXT",
       "ingestion_method": "TEXT",
       "ingestion_source": "TEXT",
       "ingestion_confidence": "TEXT",

  2. After the _add_missing_columns call and existing index creation,
     add the enforcement trigger (identical to schema.py and 0012):

       conn.execute("""
           CREATE TRIGGER IF NOT EXISTS trg_track_identity_provenance_required
           BEFORE INSERT ON track_identity
           BEGIN
               SELECT CASE
                   WHEN NEW.ingested_at IS NULL OR TRIM(NEW.ingested_at) = '' THEN
                       RAISE(ABORT, 'track_identity.ingested_at is required')
                   WHEN NEW.ingestion_method IS NULL OR TRIM(NEW.ingestion_method) = '' THEN
                       RAISE(ABORT, 'track_identity.ingestion_method is required')
                   WHEN NEW.ingestion_source IS NULL THEN
                       RAISE(ABORT, 'track_identity.ingestion_source is required')
                   WHEN NEW.ingestion_confidence IS NULL OR TRIM(NEW.ingestion_confidence) = '' THEN
                       RAISE(ABORT, 'track_identity.ingestion_confidence is required')
               END;
           END
       """)

  3. Add the three provenance indexes:
       idx_track_identity_ingested_at
       idx_track_identity_ingestion_method
       idx_track_identity_ingestion_confidence

  DO NOT modify the CREATE TABLE statement itself.

VERIFY:
  python -c "
import sqlite3
from tagslut.storage.schema import init_db
conn = sqlite3.connect(':memory:')
init_db(conn)
cols = [r[1] for r in conn.execute('PRAGMA table_info(track_identity)').fetchall()]
assert 'ingested_at' in cols, f'missing ingested_at, got {cols}'
assert 'ingestion_confidence' in cols, f'missing ingestion_confidence, got {cols}'
triggers = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='trigger'\").fetchall()]
assert 'trg_track_identity_provenance_required' in triggers, f'missing trigger, got {triggers}'
print('PASS: _ensure_v3_schema provenance columns + trigger present')
conn.close()
"

Commit: fix(schema): add provenance columns and trigger to _ensure_v3_schema legacy path

── Task 2: Fix test fixtures — tests/e2e/test_dj_pipeline.py ─────────────────

PROBLEM:
  `_insert_identity` helper does a raw INSERT with only four columns.
  After Task 1 adds the trigger to the init_db path, this will fail.

FIX:
  1. Import or inline PROV_COLS and PROV_VALS from tests/conftest.py.
     If import fails due to path issues, inline:
       _PROV_COLS = ", ingested_at, ingestion_method, ingestion_source, ingestion_confidence"
       _PROV_VALS = ", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'"

  2. Update `_insert_identity` to append provenance to column list and VALUES.

VERIFY:
  poetry run pytest tests/e2e/test_dj_pipeline.py -v

Commit: fix(tests): add provenance fields to e2e DJ pipeline test fixtures

── Task 3: Fix test fixtures — tests/metadata/test_track_db_sync.py ───────────

PROBLEM:
  Raw INSERT creates track_identity row without provenance.

FIX:
  Update INSERT INTO track_identity to include the four provenance columns:
    ingested_at = '2026-01-01T00:00:00+00:00'
    ingestion_method = 'migration'
    ingestion_source = 'test_fixture'
    ingestion_confidence = 'legacy'
  If the test creates its own CREATE TABLE for track_identity, also add
  the four columns there.

VERIFY:
  poetry run pytest tests/metadata/test_track_db_sync.py -v

Commit: fix(tests): add provenance fields to track_db_sync test fixtures

── Task 4: Fix remaining test fixtures ────────────────────────────────────────

Files:
  tests/test_verify_v3_migration.py  ~line 111
  tests/test_migration_report_v2_to_v3.py  ~line 129

DECISION RULE: Only modify a test if its DB will have the provenance trigger
(i.e., it uses create_schema_v3 or init_db after Task 1).

For each file:
  1. Read it and check whether it uses create_schema_v3 or init_db.
  2. If yes, and its INSERTs lack provenance → add the four fields.
  3. If it creates its own ad-hoc schema → leave it as-is.

The migration report test creates its own ad-hoc schema with only
(id, identity_key, isrc, enriched_at). Leave it alone.

VERIFY:
  poetry run pytest tests/test_verify_v3_migration.py -v
  poetry run pytest tests/test_migration_report_v2_to_v3.py -v

Commit: fix(tests): add provenance to remaining test fixtures that use v3 schema

── Task 5: Add CHECK constraints + update docs ────────────────────────────────

5a. Add CHECK constraints to create_schema_v3 in tagslut/storage/v3/schema.py:

  ingestion_confidence TEXT NOT NULL CHECK (
      ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy')
  ),
  ingestion_method TEXT NOT NULL CHECK (
      ingestion_method IN (
          'provider_api','isrc_lookup','fingerprint_match',
          'fuzzy_text_match','picard_tag','manual','migration',
          'multi_provider_reconcile'
      )
  ),

  Do NOT add CHECKs to the _ensure_v3_schema legacy path —
  SQLite cannot add CHECKs via ALTER TABLE.

5b. Create supabase/migrations/20260322100000_confidence_tier_check.sql:

  ALTER TABLE track_identity
    ADD CONSTRAINT chk_ingestion_confidence
    CHECK (ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy'));

  ALTER TABLE track_identity
    ADD CONSTRAINT chk_ingestion_method
    CHECK (ingestion_method IN (
        'provider_api','isrc_lookup','fingerprint_match',
        'fuzzy_text_match','picard_tag','manual','migration',
        'multi_provider_reconcile'
    ));

5c. Update docs/DB_V3_SCHEMA.md — add section documenting:
  - The four provenance columns (type, NOT NULL, purpose)
  - ingestion_confidence vocabulary table (five tiers)
  - ingestion_method vocabulary table (eight methods)
  - Enforcement trigger name and behavior
  - References to INGESTION_PROVENANCE.md and MULTI_PROVIDER_ID_POLICY.md

VERIFY:
  python -c "
import sqlite3
from tagslut.storage.v3.schema import create_schema_v3
conn = sqlite3.connect(':memory:')
create_schema_v3(conn)
try:
    conn.execute(\"\"\"
        INSERT INTO track_identity (identity_key, ingested_at, ingestion_method,
            ingestion_source, ingestion_confidence)
        VALUES ('test:bad', '2026-01-01T00:00:00+00:00', 'provider_api',
            'test', 'INVALID_TIER')
    \"\"\")
    print('FAIL: CHECK did not reject invalid confidence tier')
except sqlite3.IntegrityError as e:
    print(f'PASS: CHECK rejected invalid tier: {e}')
try:
    conn.execute(\"\"\"
        INSERT INTO track_identity (identity_key, ingested_at, ingestion_method,
            ingestion_source, ingestion_confidence)
        VALUES ('test:good', '2026-01-01T00:00:00+00:00', 'provider_api',
            'test', 'verified')
    \"\"\")
    print('PASS: valid insert accepted')
except sqlite3.IntegrityError as e:
    print(f'FAIL: valid insert rejected: {e}')
conn.close()
"

Commit: feat(schema): add CHECK constraints for ingestion_confidence and ingestion_method vocabularies

═══════════════════════════════════════════════════════
BLOCKING DECISIONS (already resolved — implement as specified)
═══════════════════════════════════════════════════════

Decision 1: dual_write.py has Optional[str] params with fallback defaults.
  This is intentional for backward compatibility. Do NOT change dual_write.py.

Decision 2: Enforcement trigger must exist in THREE places:
  1. tagslut/storage/v3/schema.py (create_schema_v3) — DONE
  2. tagslut/storage/v3/migrations/0012_ingestion_provenance.py — DONE
  3. tagslut/storage/schema.py (_ensure_v3_schema) — Task 1

═══════════════════════════════════════════════════════
ESCALATION CONDITIONS
═══════════════════════════════════════════════════════

Stop and escalate to Claude Code if:
- A test failure reveals _identity_value_map or _create_identity is
  dropping provenance fields
- The trigger in _ensure_v3_schema conflicts with an existing trigger
- Any test file creates its DB via a fourth path not covered here
- CHECK constraint rejects a value that an existing test uses

═══════════════════════════════════════════════════════
EXIT CRITERIA
═══════════════════════════════════════════════════════

All of these must be true before marking done:

  poetry run pytest tests/e2e/test_dj_pipeline.py -v              — ALL PASS
  poetry run pytest tests/metadata/test_track_db_sync.py -v       — ALL PASS
  poetry run pytest tests/test_verify_v3_migration.py -v          — ALL PASS
  poetry run pytest tests/test_migration_report_v2_to_v3.py -v   — ALL PASS
  poetry run pytest tests/test_identity_service.py -v             — ALL PASS
  poetry run pytest tests/test_db_v3_schema.py -v                 — ALL PASS

The two inline verification scripts (Tasks 1 and 5) must print PASS.
docs/DB_V3_SCHEMA.md must document provenance columns and vocabulary.

Do NOT run the full test suite. Targeted runs only per the list above.
