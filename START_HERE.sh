#!/bin/bash
# START_HERE.sh - The ONLY script you need to run to get started
# Usage: source START_HERE.sh
#
# Optional:
#   STRICT=1 source START_HERE.sh   # fail if env_exports.sh is missing

set -e  # Exit on error (note: when sourced, use 'return 1' for fatal errors)

echo "tagslut Quick Start"
echo "==================="
echo ""

# Compute project root from this script's location (portable)
TAGSLUT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TAGSLUT_ROOT

# 1. Activate virtual environment
echo "Activating Python environment..."
if [ -f "${TAGSLUT_ROOT}/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "${TAGSLUT_ROOT}/.venv/bin/activate"
    echo "   Virtual environment active"
else
    echo "   Virtual environment not found at: ${TAGSLUT_ROOT}/.venv"
    echo "   Run: cd \"${TAGSLUT_ROOT}\" && poetry install"
    return 1
fi

# 2. Load credentials and paths (optional unless STRICT=1)
echo ""
echo "Loading credentials and paths..."
if [ -f "${TAGSLUT_ROOT}/env_exports.sh" ]; then
    # shellcheck disable=SC1091
    source "${TAGSLUT_ROOT}/env_exports.sh"
    echo "   Credentials loaded from env_exports.sh"
else
    echo "   Warning: env_exports.sh not found at ${TAGSLUT_ROOT}/env_exports.sh"
    echo "   Continuing without it (set STRICT=1 to enforce)."
    if [ "${STRICT:-0}" = "1" ]; then
        return 1
    fi
fi

# 3. Set core paths (defaults only; allow user overrides)
echo ""
echo "Setting up core paths..."

: "${TAGSLUT_DB:=${TAGSLUT_ROOT}_db/FRESH_2026/music_v3.db}"
: "${MASTER_LIBRARY:=/Volumes/MUSIC/MASTER_LIBRARY}"
: "${MP3_LIBRARY:=/Volumes/MUSIC/MP3_LIBRARY}"
: "${DJ_LIBRARY:=/Volumes/MUSIC/MP3_LIBRARY}"  # DJ pool is now an M3U in MP3_LIBRARY, not a separate folder
: "${STAGING_ROOT:=/Volumes/MUSIC/staging}"

export TAGSLUT_DB
export MASTER_LIBRARY
export MP3_LIBRARY
export DJ_LIBRARY
export STAGING_ROOT

echo "   TAGSLUT_ROOT:   ${TAGSLUT_ROOT}"
echo "   TAGSLUT_DB:     ${TAGSLUT_DB}"
echo "   MASTER_LIBRARY: ${MASTER_LIBRARY}"
echo "   MP3_LIBRARY:    ${MP3_LIBRARY}"
echo "   DJ_LIBRARY:     ${DJ_LIBRARY}"
echo "   STAGING_ROOT:   ${STAGING_ROOT}"

# 4. Verify database (if possible)
echo ""
echo "Checking database..."

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "   Warning: sqlite3 is not installed or not on PATH; skipping DB check"
else
    if [ -f "$TAGSLUT_DB" ]; then
        IDENTITY_COUNT="$(sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM track_identity;" 2>/dev/null || echo "0")"
        echo "   Database found: ${IDENTITY_COUNT} track identities"
    else
        echo "   Warning: Database not found at ${TAGSLUT_DB}"
    fi
fi

# 5. Verify volumes
echo ""
echo "Checking mounted volumes..."
if [ ! -d "/Volumes/MUSIC" ]; then
    echo "   Warning: /Volumes/MUSIC not mounted - some operations will fail"
    echo "   Mount the MUSIC volume and re-run this script"
else
    echo "   /Volumes/MUSIC mounted"
fi

# 6. Show quick commands
echo ""
echo "QUICK COMMANDS (copy-paste ready):"
echo "-----------------------------------------------------"
echo ""
echo "# Download (TIDAL, Qobuz, or Beatport URL):"
echo "ts-get <url>"
echo ""
echo "# Download + add to DJ pool M3U:"
echo "ts-get <url> --dj"
echo ""
echo "# Enrich metadata (BPM, key, genre, label) for all unenriched tracks:"
echo "ts-enrich"
echo ""
echo "# Refresh all provider tokens:"
echo "ts-auth"
echo ""
echo "# When Qobuz session expires (manual re-login):"
echo "poetry run python -m tagslut auth login qobuz --email YOUR_EMAIL --force"
echo ""
echo "# Register legacy MP3-only DJ files (no FLAC master):"
echo "poetry run python -m tagslut.exec.fix_mp3_tags_from_filenames --root /Volumes/MUSIC/DJ_LIBRARY --execute"
echo "poetry run python -m tagslut index register-mp3 --execute"
echo ""
echo "# DJ pool — Rekordbox:"
echo "#   Import \$MP3_LIBRARY/dj_pool.m3u into Rekordbox"
echo "#   Build crates there, Synchronize to USB before gig"
echo ""
echo "-----------------------------------------------------"
echo ""
echo "Ready. Your environment is configured."
echo "Tip: Run 'tools/get --help' to see all options"
echo ""
