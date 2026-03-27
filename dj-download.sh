#!/bin/bash
# dj-download.sh — Download a single DJ track with --dj (enrich mode)
# 
# Usage:
#   ./dj-download.sh https://www.beatport.com/track/example/12345678
#   ./dj-download.sh https://tidal.com/browse/track/123456789
#   ./dj-download.sh --force https://tidal.com/browse/track/123456789  # skip truncation check
#
# What it does:
#   - Calls `tagslut --dj --enrich` (enrich is now default)
#   - Fetches metadata from Beatport, TIDAL, Qobuz, Discogs
#   - Verifies audio integrity (duration vs expected)
#   - Writes MP3 to $DJ_LIBRARY with full metadata
#   - Returns track identity and dedupe status
#
# Exit codes:
#   0 = success, track written to DJ_LIBRARY
#   1 = download failed (truncated, already exists, other error)
#   2 = missing URL argument
#   3 = volumes not mounted

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MASTER_LIBRARY="/Volumes/MUSIC/MASTER_LIBRARY"
DJ_LIBRARY="/Volumes/MUSIC/DJ_LIBRARY"
STAGING_ROOT="/Volumes/MUSIC/mdl"

# Parse arguments
FORCE_DOWNLOAD=false
URL=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_DOWNLOAD=true
            shift
            ;;
        http*)
            URL="$1"
            shift
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            exit 2
            ;;
    esac
done

if [ -z "$URL" ]; then
    echo -e "${RED}Error: URL required${NC}"
    echo "Usage: $0 [--force] <beatport_or_tidal_url>"
    exit 2
fi

# Verify volumes are mounted
for vol in "$MASTER_LIBRARY" "$DJ_LIBRARY" "$STAGING_ROOT"; do
    if [ ! -d "$vol" ]; then
        echo -e "${RED}Error: $vol not mounted${NC}"
        exit 3
    fi
done

echo -e "${BLUE}=== DJ Download (Enrich Mode) ===${NC}"
echo -e "URL: ${YELLOW}$URL${NC}"
echo -e "Destination: ${YELLOW}$DJ_LIBRARY${NC}"
echo ""

# Build the tagslut command
TAGSLUT_CMD="tagslut --dj --url '$URL'"

if [ "$FORCE_DOWNLOAD" = true ]; then
    echo -e "${YELLOW}[WARNING] --force-download: skipping truncation check${NC}"
    TAGSLUT_CMD="$TAGSLUT_CMD --force-download"
fi

echo -e "${BLUE}Running:${NC} $TAGSLUT_CMD"
echo ""

# Run the download
if eval "$TAGSLUT_CMD"; then
    echo -e "${GREEN}✓ Download complete${NC}"
    echo ""
    
    # Show what was written to DJ_LIBRARY
    echo -e "${BLUE}Recent files in $DJ_LIBRARY:${NC}"
    ls -lhSr "$DJ_LIBRARY" | tail -5
    
    exit 0
else
    echo -e "${RED}✗ Download failed${NC}"
    exit 1
fi
