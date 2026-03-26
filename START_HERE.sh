#!/bin/bash
# START_HERE.sh - The ONLY script you need to run to get started
# Usage: source START_HERE.sh

set -e  # Exit on error

echo "🚀 tagslut Quick Start"
echo "====================="
echo ""

# 1. Activate virtual environment
echo "📦 Activating Python environment..."
if [ -f "/Users/georgeskhawam/Projects/tagslut/.venv/bin/activate" ]; then
    source /Users/georgeskhawam/Projects/tagslut/.venv/bin/activate
    echo "   ✅ Virtual environment active"
else
    echo "   ❌ Virtual environment not found. Run: cd /Users/georgeskhawam/Projects/tagslut && poetry install"
    return 1
fi

# 2. Load credentials and paths
echo ""
echo "🔑 Loading credentials and paths..."
if [ -f "/Users/georgeskhawam/Projects/tagslut/env_exports.sh" ]; then
    source /Users/georgeskhawam/Projects/tagslut/env_exports.sh
    echo "   ✅ Credentials loaded"
else
    echo "   ❌ env_exports.sh not found"
    return 1
fi

# 3. Set core paths
echo ""
echo "📁 Setting up core paths..."
export TAGSLUT_DB="/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
export MASTER_LIBRARY="/Volumes/MUSIC/MASTER_LIBRARY"
export DJ_LIBRARY="/Volumes/MUSIC/DJ_LIBRARY"
export STAGING_ROOT="/Volumes/MUSIC/mdl"

echo "   TAGSLUT_DB: $TAGSLUT_DB"
echo "   MASTER_LIBRARY: $MASTER_LIBRARY"
echo "   DJ_LIBRARY: $DJ_LIBRARY"
echo "   STAGING_ROOT: $STAGING_ROOT"

# 4. Verify database
echo ""
echo "🗄️  Checking database..."
if [ -f "$TAGSLUT_DB" ]; then
    IDENTITY_COUNT=$(sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM track_identity;" 2>/dev/null || echo "0")
    echo "   ✅ Database found: $IDENTITY_COUNT track identities"
else
    echo "   ⚠️  Database not found at $TAGSLUT_DB"
fi

# 5. Verify volumes
echo ""
echo "💿 Checking mounted volumes..."
if [ -d "/Volumes/MUSIC" ]; then
    echo "   ✅ /Volumes/MUSIC mounted"
else
    echo "   ❌ /Volumes/MUSIC not mounted"
fi

# 6. Show quick commands
echo ""
echo "⚡ QUICK COMMANDS (copy-paste ready):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "# Download a release:"
echo "tools/get <beatport-or-tidal-url>"
echo ""
echo "# Build DJ MP3s from existing masters:"
echo "poetry run tagslut mp3 build --db \"\$TAGSLUT_DB\" --dj-root \"\$DJ_LIBRARY\" --limit 10 --execute"
echo ""
echo "# Register existing MP3s without transcoding:"
echo "poetry run tagslut mp3 reconcile --db \"\$TAGSLUT_DB\" --mp3-root \"\$DJ_LIBRARY\" --execute"
echo ""
echo "# Export Rekordbox XML:"
echo "poetry run tagslut dj backfill --db \"\$TAGSLUT_DB\""
echo "poetry run tagslut dj validate --db \"\$TAGSLUT_DB\""
echo "poetry run tagslut dj xml emit --db \"\$TAGSLUT_DB\" --out /Volumes/MUSIC/rekordbox_new.xml"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✅ Ready! Your environment is configured."
echo "💡 Tip: Run 'tools/get --help' to see all options"
echo ""
