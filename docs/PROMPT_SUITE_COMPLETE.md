# tagslut Migration Prompt Suite — Rate-Limit Safe

Complete execution guide with checkpoints, dependencies, and recovery paths.

═══════════════════════════════════════════════════════════════════════════════
PROMPT 1: VERIFY CURRENT STATE (ALWAYS RUN FIRST)
═══════════════════════════════════════════════════════════════════════════════

Purpose: Establish baseline before any changes.
Dependencies: None
Can skip if: Never (always run to know where you are)

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'VERIFY_EOF'
import sqlite3
db_path = "/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

migrations = cursor.execute(
    "SELECT version, note FROM schema_migrations WHERE schema_name='v3' ORDER BY version"
).fetchall()

print("Applied migrations:")
for v, note in migrations:
    print(f"  {v}: {note}")

applied_versions = [v for v, _ in migrations]
expected = list(range(1, 15))
missing = [v for v in expected if v not in applied_versions]

if missing:
    print(f"\n❌ MISSING: {missing}")
else:
    print("\n✅ Complete chain 1-14")

table_sql = cursor.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='track_identity'"
).fetchone()[0]

has_confidence_check = "CHECK (ingestion_confidence IN" in table_sql
has_method_check = "CHECK (ingestion_method IN" in table_sql

print(f"\nCHECK constraints:")
print(f"  ingestion_confidence: {'✅' if has_confidence_check else '❌'}")
print(f"  ingestion_method: {'✅' if has_method_check else '❌'}")

conn.close()
VERIFY_EOF

DECISION TREE:
→ Missing 13 but have 12? Run PROMPT 2
→ Have 13, missing 14? Run PROMPT 3
→ Have both 13 and 14? Run PROMPT 4 only (doc sync)
→ Missing 12? STOP — investigate

═══════════════════════════════════════════════════════════════════════════════
PROMPT 2: APPLY MIGRATION 0013
═══════════════════════════════════════════════════════════════════════════════

Purpose: Add five-tier confidence CHECK constraints
Dependencies: Migration 0012 applied, 0013 NOT applied
Can skip if: PROMPT 1 shows migration 0013 already applied

Step 1: Verify prerequisites

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'CHECK_EOF'
import sqlite3
conn = sqlite3.connect("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
cursor = conn.cursor()
versions = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3'"
).fetchall()]

if 12 not in versions:
    print("❌ ERROR: Migration 0012 NOT applied")
    exit(1)
if 13 in versions:
    print("⚠️ Migration 0013 ALREADY applied — SKIP this prompt")
    exit(0)
print("✅ Ready for migration 0013")
conn.close()
CHECK_EOF

If WARNING → Skip to PROMPT 3
If ERROR → Investigate missing migration 0012

Step 2: Apply migration

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'APPLY_EOF'
import sqlite3
from tagslut.storage.v3.migrations import migration_0013_confidence_tier_update

db_path = "/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
conn = sqlite3.connect(db_path)

print("Applying migration 0013...")
migration_0013_confidence_tier_update.up(conn)

cursor = conn.cursor()
versions_after = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3' ORDER BY version"
).fetchall()]

print(f"Migrations after: {versions_after}")

# Test enforcement
try:
    cursor.execute("""INSERT INTO track_identity (identity_key, ingested_at,
        ingestion_method, ingestion_source, ingestion_confidence)
        VALUES ('test:bad', '2026-01-01T00:00:00Z', 'provider_api',
        'test', 'INVALID')""")
    conn.rollback()
    print("❌ FAIL: Invalid confidence accepted")
except sqlite3.IntegrityError:
    print("✅ PASS: Invalid confidence rejected")

try:
    cursor.execute("""INSERT INTO track_identity (identity_key, ingested_at,
        ingestion_method, ingestion_source, ingestion_confidence)
        VALUES ('test:good', '2026-01-01T00:00:00Z', 'multi_provider_reconcile',
        'test', 'corroborated')""")
    conn.rollback()
    print("✅ PASS: Five-tier vocab accepted")
except sqlite3.IntegrityError as e:
    print(f"❌ FAIL: {e}")

conn.close()
APPLY_EOF

Step 3: Run tests

cd /Users/georgeskhawam/Projects/tagslut
poetry run pytest tests/storage/v3/test_migration_0013.py \
                 tests/storage/v3/test_migration_runner_v3.py -q

Expected: 10 passed

CHECKPOINT: Migration 0013 applied → Proceed to PROMPT 3

RATE-LIMIT RECOVERY: Re-run PROMPT 1 to verify state, then resume at failed step.

═══════════════════════════════════════════════════════════════════════════════
PROMPT 3: APPLY MIGRATION 0014  
═══════════════════════════════════════════════════════════════════════════════

Purpose: Add dj_validation_state table
Dependencies: Migration 0013 applied
Can skip if: PROMPT 1 shows migration 0014 already applied

Step 1: Verify prerequisites

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'CHECK_EOF'
import sqlite3
conn = sqlite3.connect("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
cursor = conn.cursor()
versions = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3'"
).fetchall()]

if 13 not in versions:
    print("❌ ERROR: Migration 0013 NOT applied — run PROMPT 2 first")
    exit(1)
if 14 in versions:
    print("⚠️ Migration 0014 ALREADY applied — SKIP this prompt")
    exit(0)
print("✅ Ready for migration 0014")
conn.close()
CHECK_EOF

If WARNING → Skip to PROMPT 4
If ERROR → Run PROMPT 2 first

Step 2: Apply migration

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'APPLY_EOF'
import sqlite3
from tagslut.storage.v3.migrations import migration_0014_dj_validation_state

db_path = "/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Applying migration 0014...")
migration_0014_dj_validation_state.up(conn)

versions_after = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3' ORDER BY version"
).fetchall()]
print(f"Migrations after: {versions_after}")

table_exists = cursor.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='dj_validation_state'"
).fetchone()

if table_exists:
    print("✅ dj_validation_state table created")
else:
    print("❌ ERROR: Table NOT created")

conn.close()
APPLY_EOF

Step 3: Final integrity check

cd /Users/georgeskhawam/Projects/tagslut && python3 << 'INTEGRITY_EOF'
import sqlite3
conn = sqlite3.connect("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
cursor = conn.cursor()

versions = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3' ORDER BY version"
).fetchall()]

expected = list(range(1, 15))
missing = [v for v in expected if v not in versions]

if missing:
    print(f"❌ MISSING: {missing}")
else:
    print("✅ Migration chain complete (1-14)")

for table in ['track_identity', 'asset_file', 'dj_validation_state']:
    count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {count} rows")

conn.close()
INTEGRITY_EOF

CHECKPOINT: Both migrations applied → Proceed to PROMPT 4

RATE-LIMIT RECOVERY: Re-run PROMPT 1, then resume.

═══════════════════════════════════════════════════════════════════════════════
PROMPT 4: UPDATE DOCUMENTATION (RUN AFTER MIGRATIONS)
═══════════════════════════════════════════════════════════════════════════════

Purpose: Sync docs with actual DB state
Dependencies: Migrations 0013 AND 0014 applied
Safe to run multiple times: Yes (idempotent)

Manual steps (docs editing):

1. Add to docs/PROGRESS_REPORT.md (after "Report date" line, before first session):

## Session: 2026-03-23 (pass 3) — Migration 0013/0014 Complete

**Status**: Completed — migrations 0013 and 0014 implemented, tested, and applied.

**What was done**:

1. **Migration 0013** (`0013_confidence_tier_update.py`):
   - Five-tier confidence CHECK (verified, corroborated, high, uncertain, legacy)
   - Eight-method CHECK (including multi_provider_reconcile)
   - Idempotent table recreation pattern
   - Preserves all data, recreates indexes and triggers

2. **Migration 0014** (`0014_dj_validation_state.py`):
   - Adds dj_validation_state table for DJ validation audit results
   - Supports Stage 4 XML validation gate

3. **Test coverage**: 10 tests passing

**Verification**: 10 passed

**DB state**:
- FRESH DB migrations: 1-14 complete (continuous chain)
- CHECK constraints enforce five-tier confidence vocabulary
- multi_provider_reconcile method valid

**Root cause resolution**: Migration 0012 added provenance columns but NOT CHECK 
constraints. Five-tier model was documented but never enforced. Migration 0013 
closes this gap for upgraded DBs.

---

2. Verify docs/ROADMAP.md §16 says "explicit SQLite migration" not "included in 0012"

3. Verify docs/ACTION_PLAN.md shows migrations 0013 and 0014 COMPLETE

CHECKPOINT: Documentation updated → All prompts complete

═══════════════════════════════════════════════════════════════════════════════
RATE-LIMIT RECOVERY FLOWCHART
═══════════════════════════════════════════════════════════════════════════════

If rate-limited at any point:

1. WAIT for rate limit to clear (usually 1-2 hours)
2. Re-run PROMPT 1 (verify state)
3. Based on PROMPT 1 output:
   - Missing 13? → Run PROMPT 2 from the step that failed
   - Have 13, missing 14? → Run PROMPT 3  
   - Have both? → Run PROMPT 4

Each prompt has internal checkpoints that verify prerequisites before executing.

═══════════════════════════════════════════════════════════════════════════════
