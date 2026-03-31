#!/bin/bash
# /Users/georgeskhawam/Projects/tagslut/env_exports.sh
# Single source of truth for tagslut environment configuration

# === Database ===
export TAGSLUT_DB="/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# === Volumes ===
export MASTER_LIBRARY="/Volumes/MUSIC/MASTER_LIBRARY"
export MP3_LIBRARY="/Volumes/MUSIC/MP3_LIBRARY"
export VOLUME_STAGING="/Volumes/MUSIC/mdl"
export VOLUME_WORK="/Volumes/MUSIC/_work"

# === Roots (derived from volumes) ===
export LIBRARY_ROOT="$MASTER_LIBRARY"
export ROOT_TD="$VOLUME_STAGING/tidal"      # PRIMARY: TIDAL downloads
export ROOT_BP="$VOLUME_STAGING/bpdl"       # REFERENCE: Beatport metadata only
export PLAYLIST_ROOT="$MASTER_LIBRARY/playlists"
export STAGING_ROOT="$VOLUME_STAGING"

# === Artifacts ===
export TAGSLUT_ARTIFACTS="/Users/georgeskhawam/Projects/tagslut/artifacts"
export TAGSLUT_REPORTS="$TAGSLUT_ARTIFACTS/reports"

# === Worker config ===
export SCAN_WORKERS=8
export ROON_PLAYLIST_PREFIX=""

# === TIDAL OAuth (PRIMARY download source) ===
export TIDAL_CLIENT_ID="B4mmBLyG0VC2kBEo"
export CLIENT_ID="$TIDAL_CLIENT_ID"
export REDIRECT_URI="http://localhost:8888/callback"

TIDAL_TOKENS_FILE="/Users/georgeskhawam/Projects/tagslut/tidal_tokens.json"
if [[ -f "$TIDAL_TOKENS_FILE" ]]; then
    export tidal_access_token=$(jq -r '.access_token // empty' "$TIDAL_TOKENS_FILE" 2>/dev/null)
fi

# === Beatport API (METADATA enrichment only - NOT for downloads) ===
TOKENS_FILE="${TAGSLUT_TOKENS_FILE:-$HOME/.config/tagslut/tokens.json}"
if [[ -f "$TOKENS_FILE" ]]; then
    BEATPORT_TOKEN=$(jq -r '.beatport.access_token // empty' "$TOKENS_FILE" 2>/dev/null)
    EXPIRES_AT_F=$(jq -r '.beatport.expires_at // empty' "$TOKENS_FILE" 2>/dev/null)

    if [[ -n "$BEATPORT_TOKEN" && "$BEATPORT_TOKEN" != "null" ]]; then
        export base_url="https://api.beatport.com"
        export TAGSLUT_API_BASE_URL="$base_url"
        export access_token="$BEATPORT_TOKEN"
        export TAGSLUT_API_ACCESS_TOKEN="$BEATPORT_TOKEN"

        NOW=$(date +%s)
        EXPIRES_AT_INT=$(python3 -c "import sys; print(int(float(sys.argv[1])))" "$EXPIRES_AT_F" 2>/dev/null || echo 0)
        SECONDS_LEFT=$((EXPIRES_AT_INT - NOW))

        if [[ $SECONDS_LEFT -lt 300 ]]; then
            echo "⚠️  Beatport token expires in $((SECONDS_LEFT / 60)) minutes — run: tagslut auth refresh beatport"
        fi
    fi
fi

echo "✓ tagslut environment loaded"
echo "  DB: $(basename $(dirname $TAGSLUT_DB))/$(basename $TAGSLUT_DB)"
echo "  Library: $MASTER_LIBRARY"
echo ""
echo "  PRIMARY download source: TIDAL (tiddl)"
echo "  Metadata enrichment: Beatport API"
echo ""
echo "  TIDAL staging: $ROOT_TD"
echo "  Beatport reference: $ROOT_BP"
echo ""
if [[ -n "$TAGSLUT_API_ACCESS_TOKEN" ]]; then
    HOURS_LEFT=$((SECONDS_LEFT / 3600))
    MINS_LEFT=$(((SECONDS_LEFT % 3600) / 60))
    echo "  Beatport API Token: ${TAGSLUT_API_ACCESS_TOKEN:0:10}...${TAGSLUT_API_ACCESS_TOKEN: -4}"
    echo "  Token expires in: ${HOURS_LEFT}h ${MINS_LEFT}m"
else
    echo "  Beatport API Token: ⚠️  NOT SET"
fi
