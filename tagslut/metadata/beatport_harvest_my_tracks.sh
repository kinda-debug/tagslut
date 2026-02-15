#!/usr/bin/env bash
# beatport_harvest_my_tracks.sh
#
# Harvests tracks from Beatport /v4/my/beatport/tracks/ endpoint (user's library)
# and writes normalized NDJSON rows to beatport_my_tracks.ndjson.
#
# Usage:
#   source ./env_exports.sh
#   ./beatport_harvest_my_tracks.sh
#
# Output: beatport_my_tracks.ndjson (one JSON object per line)
#
# Each NDJSON row contains:
#   service, track_id, isrc, bpm, key_name, key_camelot, genre, length_ms,
#   sample_url, release_id, release_name, label_name, title, artists, raw
#
# chmod +x beatport_harvest_my_tracks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${PROJECT_ROOT}/env_exports.sh"

OUTPUT="${BEATPORT_MY_TRACKS_NDJSON:-beatport_my_tracks.ndjson}"
LOG_FILE="${BEATPORT_MY_TRACKS_LOG:-beatport_my_tracks.log}"
STATE_FILE="${BEATPORT_MY_TRACKS_STATE:-beatport_my_tracks.state}"

RATE_LIMIT_DELAY="${RATE_LIMIT_DELAY:-3}"
RETRY_BASE_DELAY="${RETRY_BASE_DELAY:-10}"
MAX_RETRIES="${MAX_RETRIES:-5}"

# Pagination settings
PER_PAGE="${BEATPORT_PER_PAGE:-100}"
MAX_PAGES="${BEATPORT_MAX_PAGES:-1000}"

log() {
    echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "$LOG_FILE"
}

log "=========================================="
log "BEATPORT MY TRACKS HARVEST"
log "=========================================="
log "CONFIG:"
log "  OUTPUT:           $OUTPUT"
log "  PER_PAGE:         $PER_PAGE"
log "  MAX_PAGES:        $MAX_PAGES"
log "  RATE_LIMIT_DELAY: $RATE_LIMIT_DELAY"
log "=========================================="

# Check for required token
TOKEN="${BEATPORT_ACCESS_TOKEN:-}"
if [ -z "$TOKEN" ]; then
    log "ERROR: BEATPORT_ACCESS_TOKEN not set. Source env_exports.sh first."
    exit 1
fi

touch "$OUTPUT" "$LOG_FILE" "$STATE_FILE"

# Resume from last page if state file exists
LAST_PAGE=$(cat "$STATE_FILE" 2>/dev/null || echo "0")
if ! [[ "$LAST_PAGE" =~ ^[0-9]+$ ]]; then
    LAST_PAGE="0"
fi
log "Resuming from page > $LAST_PAGE"

do_with_retries() {
    local cmd="$1"
    local retries=0
    local delay="$RETRY_BASE_DELAY"

    while true; do
        set +e
        local output
        output=$(eval "$cmd" 2>&1)
        local status=$?
        set -e

        if [ $status -eq 0 ]; then
            echo "$output"
            return 0
        fi

        echo "$output" >&2

        retries=$((retries + 1))
        if [ $retries -ge "$MAX_RETRIES" ]; then
            log "ERROR: Command failed after $retries retries"
            return $status
        fi

        log "Request failed (attempt $retries), retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
    done
}

# Fetch a single page of tracks from /v4/my/beatport/tracks/
fetch_my_tracks_page() {
    local page="$1"

    local url="https://api.beatport.com/v4/my/beatport/tracks/?page=${page}&per_page=${PER_PAGE}"
    local cmd="curl -s -w '\n%{http_code}' \
        -H 'Authorization: Bearer ${TOKEN}' \
        -H 'Accept: application/json' \
        -H 'Content-Type: application/json' \
        '${url}'"

    local response
    response=$(do_with_retries "$cmd") || { echo "{}"; return 1; }

    local body status
    body=$(echo "$response" | sed '$d')
    status=$(echo "$response" | tail -n1)

    if [ "$status" = "401" ] || [ "$status" = "403" ]; then
        log "ERROR: Beatport token invalid (status $status)"
        echo "{\"error\":\"BEATPORT_AUTH\",\"http_status\":$status}"
        return 1
    fi
    if [ "$status" -ge 400 ]; then
        log "WARN: Beatport returned HTTP $status for page $page"
        echo "{\"error\":\"BEATPORT_HTTP_${status}\",\"http_status\":$status}"
        return 1
    fi

    echo "$body"
}

# Normalize a single track JSON object to our NDJSON format
# Uses jq to extract fields and build the output row
normalize_track() {
    local track_json="$1"

    echo "$track_json" | jq -c '{
        service: "beatport",
        track_id: (.id | tostring),
        isrc: (.isrc // null),
        bpm: (.bpm // null),
        key_name: (.key.name // .key // null),
        key_camelot: (.key.camelot_number // null),
        genre: (.genre.name // (if .genres then .genres[0].name else null end) // null),
        subgenre: (.sub_genre.name // (if .sub_genres then .sub_genres[0].name else null end) // null),
        length_ms: (.length_ms // null),
        sample_url: (.sample_url // .preview.sample_url // null),
        release_id: (.release.id // null),
        release_name: (.release.name // null),
        label_name: (.release.label.name // .label.name // null),
        title: (.name // null),
        mix_name: (.mix_name // null),
        artists: [.artists[]?.name] | if length == 0 then null else . end,
        remixers: [.remixers[]?.name] | if length == 0 then null else . end,
        catalog_number: (.catalog_number // .release.catalog_number // null),
        publish_date: (.publish_date // .new_release_date // null),
        artwork_url: (.release.image.uri // .image.uri // null),
        raw: .
    }'
}

# Main pagination loop
PAGE=$((LAST_PAGE + 1))
TOTAL_TRACKS=0

while [ "$PAGE" -le "$MAX_PAGES" ]; do
    log "Fetching page $PAGE..."

    PAGE_JSON=$(fetch_my_tracks_page "$PAGE")

    # Check for errors
    if echo "$PAGE_JSON" | jq -e '.error' > /dev/null 2>&1; then
        log "ERROR: Failed to fetch page $PAGE"
        break
    fi

    # Extract results array
    RESULTS=$(echo "$PAGE_JSON" | jq -c '.results // []')
    RESULT_COUNT=$(echo "$RESULTS" | jq 'length')

    if [ "$RESULT_COUNT" -eq 0 ]; then
        log "No more results at page $PAGE. Harvest complete."
        break
    fi

    log "  Processing $RESULT_COUNT tracks from page $PAGE..."

    # Process each track in the results
    echo "$RESULTS" | jq -c '.[]' | while read -r track; do
        normalized=$(normalize_track "$track")
        echo "$normalized" >> "$OUTPUT"
        TOTAL_TRACKS=$((TOTAL_TRACKS + 1))
    done

    # Update state
    echo "$PAGE" > "$STATE_FILE"

    # Check if we've reached the last page
    TOTAL_PAGES=$(echo "$PAGE_JSON" | jq '.count // 0')
    CURRENT_COUNT=$((PAGE * PER_PAGE))
    if [ "$CURRENT_COUNT" -ge "$TOTAL_PAGES" ] 2>/dev/null; then
        log "Reached end of results (total: $TOTAL_PAGES tracks)"
        break
    fi

    PAGE=$((PAGE + 1))

    log "  Sleeping ${RATE_LIMIT_DELAY}s before next page..."
    sleep "$RATE_LIMIT_DELAY"
done

FINAL_COUNT=$(wc -l < "$OUTPUT" | tr -d ' ')
log "=========================================="
log "Harvest complete."
log "  Total NDJSON rows: $FINAL_COUNT"
log "  Output file: $OUTPUT"
log "=========================================="
