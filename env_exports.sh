#!/bin/bash
# /Users/georgeskhawam/Projects/tagslut/env_exports.sh
# Single source of truth for tagslut environment configuration

# === Database ===
export TAGSLUT_DB="/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres"

# === Volumes ===
export MASTER_LIBRARY="/Volumes/MUSIC/MASTER_LIBRARY"
export DJ_LIBRARY="/Volumes/MUSIC/DJ_LIBRARY"
export VOLUME_STAGING="/Volumes/MUSIC/mdl"
export VOLUME_WORK="/Volumes/MUSIC/_work"

# === Roots (derived from volumes) ===
export LIBRARY_ROOT="$MASTER_LIBRARY"
export DJ_MP3_ROOT="$DJ_LIBRARY"
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
BEATPORTDL_CREDS="/Users/georgeskhawam/Projects/beatportdl/beatportdl-credentials.json"
if [[ -f "$BEATPORTDL_CREDS" ]]; then
    BEATPORT_TOKEN=$(jq -r '.access_token' "$BEATPORTDL_CREDS" 2>/dev/null)
    ISSUED_AT=$(jq -r '.issued_at' "$BEATPORTDL_CREDS" 2>/dev/null)
    EXPIRES_IN=$(jq -r '.expires_in' "$BEATPORTDL_CREDS" 2>/dev/null)
    
    if [[ -n "$BEATPORT_TOKEN" && "$BEATPORT_TOKEN" != "null" ]]; then
        export base_url="https://api.beatport.com"
        export TAGSLUT_API_BASE_URL="$base_url"
        export access_token="$BEATPORT_TOKEN"
        export TAGSLUT_API_ACCESS_TOKEN="$BEATPORT_TOKEN"
        
        EXPIRES_AT=$((ISSUED_AT + EXPIRES_IN))
        NOW=$(date +%s)
        SECONDS_LEFT=$((EXPIRES_AT - NOW))
        
        if [[ $SECONDS_LEFT -lt 300 ]]; then
            echo "⚠️  Beatport token expires in $((SECONDS_LEFT / 60)) minutes"
            echo "   Run: cd /Users/georgeskhawam/Projects/beatportdl && ./beatportdl-darwin-arm64 --help"
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
