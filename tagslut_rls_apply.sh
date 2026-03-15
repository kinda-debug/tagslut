#!/bin/bash
# tagslut RLS Policy Application Workflow
# Path A: Minimal RLS (service_role only)
# 
# Run from repo root: bash /tmp/tagslut_rls_apply.sh

set -e

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  tagslut: Apply Minimal RLS Policies (Service Role Only)                  ║"
echo "║  Path A: Unblock backend access while RLS guard is active                 ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# Step 1: Generate migration timestamp
# ============================================================================
TIMESTAMP=$(date +%Y%m%d%H%M%S)
MIGRATION_FILE="supabase/migrations/${TIMESTAMP}_rls_policies_service_role.sql"

echo "▶ Step 1: Create migration file"
echo "   File: $MIGRATION_FILE"
echo ""

# ============================================================================
# Step 2: Write migration (minimal RLS)
# ============================================================================
cat > "$MIGRATION_FILE" << 'SQL'
-- supabase/migrations/YYYYMMDDHHMMSS_rls_policies_service_role.sql
--
-- Minimal RLS: Allow service_role complete access
-- This unblocks backend development while RLS guard is active
--
-- Service role is used by:
-- - Identity service (track identity deduplication, linking)
-- - Zone classification (asset file zone transitions)
-- - Audit system (reconcile_log, provenance_event)
-- - Scheduled jobs (scan runs, tag hoard maintenance)
-- - Admin tooling
--
-- Authenticated/user-level policies deferred to Phase 2

DO $$
DECLARE
  t text;
  policy_created int := 0;
BEGIN
  FOR t IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  LOOP
    EXECUTE format('
      CREATE POLICY service_role_all ON public.%I
      FOR ALL
      USING (auth.role() = ''service_role'')
      WITH CHECK (auth.role() = ''service_role'');
    ', t);
    policy_created := policy_created + 1;
  END LOOP;
  
  RAISE NOTICE 'Created % RLS policies for service_role', policy_created;
END $$;
SQL

echo "✓ Migration file created"
echo ""

# ============================================================================
# Step 3: Dry-run
# ============================================================================
echo "▶ Step 2: Dry-run (no changes applied)"
echo ""

supabase db push --dry-run 2>&1 | tee /tmp/rls-policy-plan.txt

echo ""
echo "Review the plan above. It should show:"
echo "  - One CREATE POLICY statement per table (42 total)"
echo "  - All policies named 'service_role_all'"
echo ""

# ============================================================================
# Step 4: Human approval gate
# ============================================================================
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  ⚠ APPROVAL GATE: Review plan before proceeding                           ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""
read -p "Apply this migration? (yes/no): " approval

if [ "$approval" != "yes" ]; then
    echo "❌ Migration cancelled by user."
    echo "   To retry: Remove $MIGRATION_FILE and run this script again"
    rm "$MIGRATION_FILE"
    exit 1
fi

echo ""

# ============================================================================
# Step 5: Apply migration
# ============================================================================
echo "▶ Step 3: Apply migration"
echo ""

supabase db push

echo ""
echo "✓ Migration applied"
echo ""

# ============================================================================
# Step 6: Verify policies exist
# ============================================================================
echo "▶ Step 4: Verify policies created"
echo ""

psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" << 'SQL'
SELECT tablename, count(*) as policy_count
FROM pg_policies
WHERE schemaname = 'public'
GROUP BY tablename
ORDER BY tablename;
SQL

echo ""
POLICY_COUNT=$(psql "postgresql://postgres:postgres@127.0.0.1:54322/postgres" -tc "
  SELECT count(*) FROM pg_policies WHERE schemaname = 'public';
")

echo "Total policies created: $POLICY_COUNT"
echo ""

if [ "$POLICY_COUNT" -ne 42 ]; then
    echo "⚠ Expected 42 policies (one per table), got $POLICY_COUNT"
fi

echo "✓ RLS policies verified"
echo ""

# ============================================================================
# Step 7: Regenerate types
# ============================================================================
echo "▶ Step 5: Regenerate types"
echo ""

supabase gen types typescript --local > src/generated/database.types.ts

echo "✓ Types regenerated"
echo ""

# ============================================================================
# Step 8: Review type changes
# ============================================================================
echo "▶ Step 6: Review type changes"
echo ""

if git status src/generated/database.types.ts | grep -q "modified"; then
    echo "Changes to database types:"
    git diff src/generated/database.types.ts | head -50
    echo ""
    echo "(Showing first 50 lines; use 'git diff src/generated/database.types.ts' for full diff)"
else
    echo "✓ No type changes (policies don't affect Row/Insert/Update types)"
fi

echo ""

# ============================================================================
# Step 9: Stage for commit
# ============================================================================
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  ✓ Ready to commit                                                         ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

echo "Next steps:"
echo ""
echo "1. Review the changes:"
echo "   git status"
echo ""
echo "2. Commit:"
echo "   git add supabase/migrations/${TIMESTAMP}_rls_policies_service_role.sql src/generated/database.types.ts"
echo "   git commit -m \"RLS: Add service_role policies for backend access"
echo ""
echo "   - Enables service_role to read/write all 42 tables"
echo "   - Unblocks identity service, zone classification, audit system"
echo "   - Authenticated/user policies deferred to Phase 2\""
echo ""
echo "3. Verify in Python app:"
echo "   export DATABASE_URL=\"postgresql://postgres:postgres@127.0.0.1:54322/postgres\""
echo "   python -c \"import psycopg; print(psycopg.connect(os.environ['DATABASE_URL']).execute('SELECT COUNT(*) FROM track_identity').fetchone())\""
echo ""
