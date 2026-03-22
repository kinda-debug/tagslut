#!/bin/bash
# tagslut-supabase-check.sh
# 
# Diagnostic script to verify Supabase setup before delegating work to Claude Code
# Run: bash tagslut-supabase-check.sh
# 
# Output: Summary of setup state + actionable feedback

set -e

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  tagslut Supabase Diagnostic Check                                        ║"
echo "║  Generated: $(date)                                               ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

ERRORS=0
WARNINGS=0

# ============================================================================
# Check 1: Docker & Supabase Stack
# ============================================================================
echo "▶ Checking Docker & Supabase Stack..."
echo ""

if ! command -v docker &> /dev/null; then
    echo "  ✗ Docker not installed"
    ((ERRORS++))
else
    echo "  ✓ Docker found: $(docker --version)"
fi

if ! docker ps &> /dev/null; then
    echo "  ✗ Docker daemon not accessible (is Docker running?)"
    ((ERRORS++))
else
    if docker ps | grep -q supabase; then
        echo "  ✓ Supabase containers running"
    else
        echo "  ✗ Supabase containers not running"
        echo "     Fix: supabase start"
        ((ERRORS++))
    fi
fi

if ! command -v supabase &> /dev/null; then
    echo "  ✗ Supabase CLI not installed"
    echo "     Fix: npm install -g supabase"
    ((ERRORS++))
else
    echo "  ✓ Supabase CLI found: $(supabase --version)"
fi

echo ""

# ============================================================================
# Check 2: Database Connectivity
# ============================================================================
echo "▶ Checking Database Connectivity..."
echo ""

DB_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"

if ! command -v psql &> /dev/null; then
    echo "  ⚠ psql not installed (cannot verify database connectivity)"
    ((WARNINGS++))
else
    if psql "$DB_URL" -c "SELECT 1;" &> /dev/null; then
        echo "  ✓ Database accessible at $DB_URL"
    else
        echo "  ✗ Cannot connect to database at $DB_URL"
        echo "     Ensure Supabase is running: supabase start"
        ((ERRORS++))
    fi
fi

echo ""

# ============================================================================
# Check 3: Supabase Status
# ============================================================================
echo "▶ Checking Supabase Status..."
echo ""

if supabase status &> /tmp/supabase-status.txt; then
    cat /tmp/supabase-status.txt | head -20
    echo ""
else
    echo "  ✗ supabase status failed"
    ((ERRORS++))
fi

echo ""

# ============================================================================
# Check 4: Migration Files
# ============================================================================
echo "▶ Checking Migration Files..."
echo ""

if [ ! -d "supabase/migrations" ]; then
    echo "  ✗ supabase/migrations/ directory not found"
    ((ERRORS++))
else
    MIGRATION_COUNT=$(ls -1 supabase/migrations/*.sql 2>/dev/null | wc -l)
    if [ "$MIGRATION_COUNT" -eq 0 ]; then
        echo "  ✗ No migration files found in supabase/migrations/"
        ((ERRORS++))
    else
        echo "  ✓ Found $MIGRATION_COUNT migration files:"
        ls -1 supabase/migrations/*.sql | head -5 | sed 's/^/     - /'
        if [ "$MIGRATION_COUNT" -gt 5 ]; then
            echo "     ... and $((MIGRATION_COUNT - 5)) more"
        fi
    fi
fi

# Check for uncommitted migrations
if ! git status supabase/migrations/ &> /dev/null; then
    echo "  ⚠ Git status check failed (may not be in git repo)"
else
    if git status supabase/migrations/ | grep -q "modified\|new file"; then
        echo "  ⚠ Uncommitted changes in supabase/migrations/"
        git status supabase/migrations/ | grep -E "modified|new file" | sed 's/^/     /'
        ((WARNINGS++))
    else
        echo "  ✓ All migration files committed"
    fi
fi

echo ""

# ============================================================================
# Check 5: Schema State (if connected)
# ============================================================================
echo "▶ Checking Schema State..."
echo ""

if ! psql "$DB_URL" -c "SELECT 1;" &> /dev/null; then
    echo "  ⚠ Cannot check schema (database not accessible)"
else
    # Count tables
    TABLE_COUNT=$(psql "$DB_URL" -c "
        SELECT COUNT(*)::text FROM information_schema.tables
        WHERE table_schema = 'public';" 2>/dev/null | tail -2 | head -1 | xargs)
    
    if [ ! -z "$TABLE_COUNT" ]; then
        echo "  ✓ Schema loaded: $TABLE_COUNT public tables"
    fi

    # Check critical tables
    CRITICAL_TABLES=("track_identity" "asset_link" "asset_file")
    for table in "${CRITICAL_TABLES[@]}"; do
        if psql "$DB_URL" -c "SELECT 1 FROM information_schema.tables WHERE table_name='$table';" 2>/dev/null | grep -q "1"; then
            COUNT=$(psql "$DB_URL" -c "SELECT COUNT(*) FROM $table;" 2>/dev/null | tail -2 | head -1 | xargs)
            echo "  ✓ Table $table exists ($COUNT records)"
        else
            echo "  ✗ Critical table $table not found"
            ((ERRORS++))
        fi
    done

    # Check RLS status
    echo ""
    echo "  RLS Status:"
    RLS_ENABLED=$(psql "$DB_URL" -c "
        SELECT COUNT(*) FROM pg_tables
        WHERE schemaname='public' AND rowsecurity;" 2>/dev/null | tail -2 | head -1 | xargs)
    
    RLS_TOTAL=$(psql "$DB_URL" -c "
        SELECT COUNT(*) FROM pg_tables
        WHERE schemaname='public';" 2>/dev/null | tail -2 | head -1 | xargs)
    
    if [ "$RLS_ENABLED" -eq "$RLS_TOTAL" ]; then
        echo "  ✓ RLS enabled on all $RLS_TOTAL public tables"
    else
        echo "  ⚠ RLS enabled on $RLS_ENABLED of $RLS_TOTAL tables"
        ((WARNINGS++))
    fi

    # Check RLS policies exist
    POLICIES=$(psql "$DB_URL" -c "
        SELECT COUNT(*) FROM pg_policies WHERE schemaname='public';" 2>/dev/null | tail -2 | head -1 | xargs)
    
    if [ "$POLICIES" -eq 0 ]; then
        echo "  ⚠ No RLS policies defined (tables locked down, API access will fail)"
        ((WARNINGS++))
    else
        echo "  ✓ RLS policies exist: $POLICIES policies"
    fi
fi

echo ""

# ============================================================================
# Check 6: Generated Types
# ============================================================================
echo "▶ Checking Generated Types..."
echo ""

if [ ! -f "src/generated/database.types.ts" ]; then
    echo "  ✗ src/generated/database.types.ts not found"
    echo "     Fix: supabase gen types typescript --local > src/generated/database.types.ts"
    ((ERRORS++))
else
    LINES=$(wc -l < src/generated/database.types.ts)
    echo "  ✓ Types file exists ($LINES lines)"
    
    # Check if committed
    if ! git status src/generated/database.types.ts &> /dev/null; then
        echo "  ⚠ Cannot check git status"
    elif git status src/generated/database.types.ts | grep -q "modified"; then
        echo "  ⚠ src/generated/database.types.ts has uncommitted changes"
        ((WARNINGS++))
    else
        echo "  ✓ Types file committed"
    fi
fi

echo ""

# ============================================================================
# Check 7: Environment Variables
# ============================================================================
echo "▶ Checking Environment Variables..."
echo ""

if [ -z "$DATABASE_URL" ]; then
    echo "  ⚠ DATABASE_URL not set"
    echo "     Recommended: export DATABASE_URL=\"$DB_URL\""
    ((WARNINGS++))
else
    echo "  ✓ DATABASE_URL set to: $DATABASE_URL"
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║  SUMMARY                                                                   ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
    echo "✓ All checks passed. Safe to delegate work to Claude Code."
    echo ""
    echo "Suggested next steps:"
    echo "  1. Review pending migrations: supabase migration list"
    echo "  2. Dry-run next migration: supabase db push --dry-run"
    echo "  3. If ready: supabase db push"
    exit 0
elif [ "$ERRORS" -eq 0 ]; then
    echo "⚠ All critical checks passed ($WARNINGS warnings found)."
    echo ""
    echo "Review warnings above and fix before delegating sensitive work."
    exit 0
else
    echo "✗ ERRORS FOUND: Fix $ERRORS error(s) before proceeding."
    echo ""
    echo "Run this script again after fixes to verify."
    exit 1
fi
