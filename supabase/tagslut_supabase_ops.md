# tagslut Supabase Operations Manual

## Current Schema State (as of 2025-03-15)

### Baseline Facts
- **Migration baseline:** `20260315154756_tagslut_schema.sql` (42 tables, ~32k track_identity records)
- **Security layer:** `20260315180508_enable_rls.sql` (RLS enabled across all public tables)
- **Type generation:** `src/generated/database.types.ts` (TypeScript Row/Insert/Update interfaces)
- **Local stack:** PostgreSQL via Supabase, available at `postgresql://postgres:postgres@127.0.0.1:54322/postgres`
- **Remote state:** Empty (migrations created locally, not yet pushed to Supabase Platform)

### Tables & Relationships (Critical Path)
- `track_identity` (32,196 records) — DJ track metadata, keyed by `identity_key`
- `asset_link` — Maps assets to identities; FK to `track_identity.id`
- `asset_file` — File variants; FK to `asset_link.id`
- `library_tracks` — User library associations
- `tag_hoard_values` — Metadata tagging system
- Plus 36 more tables (full schema in migration file)

### Security Posture
- RLS enabled on all public tables
- No RLS policies defined yet (tables are locked down, but policies need to be explicit)
- API access will fail until policies are created

---

## Pre-Migration Checklist (Before Any `supabase db push`)

Use this before running migrations in Claude Code or locally.

### 1. Docker & Supabase Stack
```bash
# Is Docker running?
docker ps | grep -q supabase && echo "✓ Supabase running" || echo "✗ Supabase not running"

# Get local DB URL
supabase status | grep "DB URL:"

# Test connectivity
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "SELECT 1;" && echo "✓ DB accessible" || echo "✗ DB not accessible"
```

### 2. Migration File Inventory
```bash
# What migrations are in the repo?
ls -la supabase/migrations/

# What's already applied locally?
supabase migration list

# Are there uncommitted migrations?
git status supabase/migrations/
```

### 3. Schema State Snapshot (Before Changes)
```bash
# Dump current schema
supabase db dump --schema public --local -f /tmp/schema-before.json --format=json 2>/dev/null || \
  psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "\dt public.*;" > /tmp/schema-before.txt

# Check row counts (early warning if data is corrupt)
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" << 'SQL'
SELECT tablename, n_live_tup as row_count
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC
LIMIT 10;
SQL

# Store critical counts
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "SELECT COUNT(*) as track_identity_count FROM track_identity;" > /tmp/baseline-counts.txt
```

### 4. Type Generation State
```bash
# Current types file hash (to detect changes)
shasum src/generated/database.types.ts > /tmp/types-before.sha

# Are generated types committed?
git status src/generated/database.types.ts
```

---

## Safe Migration Workflow (For Claude Code)

### Step 1: Dry-Run (No Side Effects)
```bash
supabase db push --dry-run 2>&1 | tee /tmp/migration-dry-run.log
```

**What to look for in output:**
- List of SQL commands that will execute
- Any errors (connection refused, constraint violations, etc.)
- Data-destructive operations (DROP TABLE, ALTER COLUMN TYPE, etc.)
- Expected vs. unexpected schema changes

**Save this file; you'll need it if migration fails.**

### Step 2: Review the Plan (Human Decision Point)
```bash
cat /tmp/migration-dry-run.log
```

**Ask yourself:**
- Does the SQL match what the migration file says?
- Are there any DROP/ALTER operations that weren't in the migration?
- Do you see the new tables/columns you added?
- Any foreign key conflicts?

**If anything looks wrong:** Stop here. Do NOT proceed to Step 3.

### Step 3: Apply Migration (After Approval)
```bash
supabase db push
```

**Verify success:**
```bash
echo "Checking migration status..."
supabase migration list | grep -E "Success|Failed"

echo "Checking row counts post-migration..."
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "SELECT COUNT(*) as track_identity_count FROM track_identity;"
```

### Step 4: Regenerate Types (After Schema Confirmed)
```bash
supabase gen types typescript --local > src/generated/database.types.ts
```

**Verify changes:**
```bash
git diff src/generated/database.types.ts | head -50
```

**Is the diff what you expected?**
- New columns → new properties in Row/Insert/Update interfaces?
- New tables → new Table types?
- Removed columns → properties gone?

If diff looks wrong, investigate before committing.

### Step 5: Commit (After Verification)
```bash
git add supabase/migrations/<new-migration>.sql src/generated/database.types.ts
git commit -m "Migration: <description>

- Schema: Added/modified <tables>
- Dry-run log: /tmp/migration-dry-run.log
- Row counts verified: track_identity still 32k+
- RLS policies: [Updated/No change]"
```

---

## Debugging: Common Failure Modes

### Docker Not Running
```
Error: Cannot connect to Docker daemon
```
**Fix:**
```bash
docker ps  # If fails, start Docker Desktop or run: dockerd
supabase start
```

### Connection Pool Exhausted
```
Error: too many connections for role "postgres"
```
**Fix:**
```bash
supabase stop
supabase start
```

### Foreign Key Constraint Violation
```
Error: insert or update on table "asset_file" violates foreign key constraint
```
**Diagnosis:**
```bash
# Check orphaned rows (asset_file records with asset_link.id that doesn't exist)
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" << 'SQL'
SELECT af.id, af.asset_id
FROM asset_file af
LEFT JOIN asset_link al ON af.asset_id = al.id
WHERE al.id IS NULL;
SQL
```

**Fix:** Depends on data state. If orphaned records exist, either:
- Delete them: `DELETE FROM asset_file WHERE asset_id NOT IN (SELECT id FROM asset_link);`
- Or restore schema to a known-good state: `supabase stop && supabase start`

### RLS Blocking Access
```
Error: new row violates row-level security policy for table "track_identity"
```
**Diagnosis:**
```bash
# Check if RLS is actually enabled
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "
  SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public';
"

# Check if any policies exist
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -c "
  SELECT schemaname, tablename, policyname FROM pg_policies WHERE schemaname='public';
"
```

**Fix:** If RLS is enabled but no policies exist, either:
- Create policies (e.g., allow authenticated users, allow service role):
```sql
CREATE POLICY allow_all ON public.track_identity
  FOR SELECT
  USING (auth.role() IN ('authenticated', 'service_role'));
```
- Or temporarily disable RLS for development:
```sql
ALTER TABLE public.track_identity DISABLE ROW LEVEL SECURITY;
```

### Types Out of Sync with Schema
```bash
# Regenerate and check
supabase gen types typescript --local > /tmp/new-types.ts
diff src/generated/database.types.ts /tmp/new-types.ts
```

**Fix:** If diff shows schema changes not reflected in committed types:
```bash
cp /tmp/new-types.ts src/generated/database.types.ts
git add src/generated/database.types.ts
git commit -m "Update types to match schema"
```

---

## Assumptions Document: tagslut Schema Invariants

### Core Identity Model
**Tables:** `track_identity`, `asset_link`, `asset_file`

**Invariants:**
- `track_identity.identity_key` is immutable (never renamed, retyped, or moved)
- `asset_link.identity_id` → `track_identity.id` is one-to-many (one identity can have multiple asset links)
- `asset_file.asset_id` → `asset_link.id` is one-to-many (one link can have multiple file variants)
- No cascading deletes on these foreign keys (preserve audit trail)

**Violating these means:**
- Identity service breaks
- Zone classification logic fails
- Move-only semantics undefined

### Zone Classification (if implemented)
**Tables:** `zone_accepted`, `zone_staging`, `zone_suspect`, `zone_quarantine` (or single table with zone enum)

**Assumptions:**
- Every asset_file must be in exactly one zone at any time
- Zone transitions are audited (insert into zone_audit table)
- Backfill, staging, and suspect zones are temporary; accepted is terminal

### Row-Level Security
**Current state:** RLS enabled, no policies defined (all access blocked)

**Next phase:** Define policies like:
```sql
-- Allow authenticated users to read their own library_tracks
CREATE POLICY user_library_read ON public.library_tracks
  FOR SELECT
  USING (user_id = auth.uid());

-- Allow service role (backend) full access
CREATE POLICY service_role_full ON public.library_tracks
  FOR ALL
  USING (auth.role() = 'service_role');
```

---

## Supabase CLI Commands for Claude Code

### Safe Read-Only Commands (Always Safe)
```bash
# Check stack status
supabase status

# List applied migrations
supabase migration list

# Inspect schema (dry-run, doesn't apply)
supabase db push --dry-run

# Dump schema for inspection
supabase db dump --schema public --local

# Generate types
supabase gen types typescript --local
```

### Dangerous Commands (Use with Caution)
```bash
# Apply migrations (modifies in-memory DB state)
supabase db push

# Reset entire local stack (DESTRUCTIVE)
supabase reset
supabase stop && supabase start

# Directly connect to running DB (allows arbitrary SQL)
psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
```

---

## Environment Variables for Python/Node.js Apps

Set in `.env` or shell:

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"
SUPABASE_ANON_KEY="<from supabase status>"
SUPABASE_SERVICE_ROLE_KEY="<from supabase status>"
```

Applications can then:
```python
import os
conn = psycopg.connect(os.environ["DATABASE_URL"])
```

---

## Before Pushing to Remote Supabase Project

If/when you link to a remote Supabase instance:

### 1. Verify Remote is Empty
```bash
supabase projects list
# Note the remote project ref

supabase db list
# Should show 0 applied migrations if fresh project
```

### 2. Set Remote Link
```bash
supabase link --project-ref <PROJECT-REF>
```

### 3. Dry-Run Against Remote
```bash
supabase db push --dry-run
# This will show what *would* be applied to production
```

### 4. Only After Approval: Push
```bash
supabase db push
```

### 5. Verify Remote Schema
```bash
supabase db list  # Show remote migrations
psql <remote-connection-string> -c "SELECT COUNT(*) FROM track_identity;"
```

---

## Checklist: Safe Migration Pattern (Copy This)

Before delegating any DB work to Claude Code:

- [ ] Docker running? `docker ps | grep supabase`
- [ ] Local stack healthy? `supabase status`
- [ ] No uncommitted migration files? `git status supabase/migrations/`
- [ ] Types file current? `git status src/generated/database.types.ts`
- [ ] Baseline row counts saved? `psql ... -c "SELECT COUNT(*) FROM track_identity;"`
- [ ] Dry-run passing? `supabase db push --dry-run | tee /tmp/plan.txt`
- [ ] Reviewed the plan? Did you read /tmp/plan.txt?
- [ ] Ready to apply? Then: `supabase db push`
- [ ] Regenerate types? `supabase gen types typescript --local > src/generated/database.types.ts`
- [ ] Types diff reviewed? `git diff src/generated/database.types.ts`
- [ ] All committed? `git status`

---

## Claude Code Bootstrap Context

Paste this when asking Claude Code to work on tagslut database tasks:

```
## tagslut Database Context (Phase 1 Refactor)

**Schema:** PostgreSQL via Supabase (42 tables, 32k+ track_identity records)
**Migrations:** Baseline (20260315154756) + RLS (20260315180508)
**Security:** RLS enabled on all public tables; policies TBD
**Types:** Generated at src/generated/database.types.ts

**Before any schema changes:**
1. supabase db push --dry-run | tee /tmp/plan.txt
2. Review /tmp/plan.txt for expected changes
3. Only then: supabase db push
4. Verify: supabase migration list
5. Regenerate: supabase gen types typescript --local > src/generated/database.types.ts
6. Review: git diff src/generated/database.types.ts

**DO NOT:**
- Run supabase db push without dry-run first
- Commit generated types without reviewing schema changes
- Drop/rename identity_key, asset_link, or asset_file
- Mix local migrations with remote db pull

**Current state:** [Docker running? Stack healthy? Types current? All committed?]
```

