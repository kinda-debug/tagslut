#!/usr/bin/env bash
# beatport_harvest_catalog_track.sh
#
# Fetches a single track from Beatport /v4/catalog/tracks/{id}/ endpoint
# and outputs normalized JSON to stdout or appends to NDJSON file.
#
# Usage:
#   ./beatport_harvest_catalog_track.sh 23011269
#   ./beatport_harvest_catalog_track.sh 23011269 >> beatport_catalog_tracks.ndjson
#
# For batch processing, pipe track IDs:
#   cat track_ids.txt | while read id; do ./beatport_harvest_catalog_track.sh "$id"; done > output.ndjson
#
# chmod +x beatport_harvest_catalog_track.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Get Beatport token from TokenManager (System B)
if ! BEATPORT_ACCESS_TOKEN="$(tagslut auth token-get beatport 2>/dev/null)"; then
    echo "ERROR: No valid Beatport token." >&2
    echo "Run: tagslut auth login beatport" >&2
    exit 1
fi
export BEATPORT_ACCESS_TOKEN

RETRY_BASE_DELAY="${RETRY_BASE_DELAY:-10}"
MAX_RETRIES="${MAX_RETRIES:-5}"

# Check for track ID argument
if [ $# -lt 1 ]; then
    echo "Usage: $0 <track_id>" >&2
    echo "Example: $0 23011269" >&2
    exit 1
fi

TRACK_ID="$1"

# Check for required token
TOKEN="${BEATPORT_ACCESS_TOKEN}"

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

        retries=$((retries + 1))
        if [ $retries -ge "$MAX_RETRIES" ]; then
            echo "ERROR: Command failed after $retries retries" >&2
            return $status
        fi

        sleep "$delay"
        delay=$((delay * 2))
    done
}

# Fetch track from catalog endpoint
fetch_catalog_track() {
    local track_id="$1"

    local url="https://api.beatport.com/v4/catalog/tracks/${track_id}/"
    local cmd="curl -s -w '\n%{http_code}' \
        -H 'Authorization: Bearer ${TOKEN}' \
        -H 'Accept: application/json' \
        '${url}'"

    local response
    response=$(do_with_retries "$cmd") || { echo "{}"; return 1; }

    local body status
    body=$(echo "$response" | sed '$d')
    status=$(echo "$response" | tail -n1)

    if [ "$status" = "401" ] || [ "$status" = "403" ]; then
        echo "{\"error\":\"BEATPORT_AUTH\",\"http_status\":$status,\"track_id\":\"$track_id\"}"
        return 1
    fi
    if [ "$status" = "404" ]; then
        echo "{\"error\":\"NOT_FOUND\",\"http_status\":404,\"track_id\":\"$track_id\"}"
        return 1
    fi
    if [ "$status" -ge 400 ]; then
        echo "{\"error\":\"BEATPORT_HTTP_${status}\",\"http_status\":$status,\"track_id\":\"$track_id\"}"
        return 1
    fi

    echo "$body"
}

# Normalize track JSON to standard format
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

# Main execution
RAW_JSON=$(fetch_catalog_track "$TRACK_ID")

# Check for errors in response
if echo "$RAW_JSON" | jq -e '.error' > /dev/null 2>&1; then
    echo "$RAW_JSON"
    exit 1
fi

# Normalize and output
normalize_track "$RAW_JSON"
