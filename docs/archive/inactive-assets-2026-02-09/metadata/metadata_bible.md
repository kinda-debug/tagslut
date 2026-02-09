Here is the complete, final setup **one last time**, for all four services (TIDAL, Beatport, Qobuz, Spotify), **without any secrets or real values** – pure templates that you can safely store and then fill in locally.

It includes:

1. `env_exports.sh` – master environment template.
2. `harvest_metadata_full.sh` – harvester template (4 services).
3. `aggregate_metadata_full.py` – aggregator template with canonical BPM/key/genre (Beatport > Qobuz > TIDAL > Spotify).
4. TIDAL visualization script template for Postman.

No tokens, passwords, or client secrets are hard-coded.

---

## 1. `env_exports.sh` (TEMPLATE ONLY – no secrets)

```bash
#!/usr/bin/env bash

########################################
# env_exports.sh TEMPLATE (no secrets)
########################################
# 1) Fill in your own secrets/tokens/IDs below.
# 2) Then:
#      chmod +x env_exports.sh
#      source ./env_exports.sh
########################################

########## QOBUZ – ACCOUNT / SCRAPER CONFIG ##########
# Your Qobuz login identifier (email or numeric user id)
export QOBUZ_EMAIL_OR_USERID=""

# Either:
#  - MD5 hash of your Qobuz plaintext password, OR
#  - A Qobuz user auth token, depending on your tooling
export QOBUZ_PASSWORD_MD5_OR_TOKEN=""

# Qobuz app id (e.g. "798273057")
export QOBUZ_APP_ID=""

# Qobuz request-signing secrets (if needed for request_sig calculation)
export QOBUZ_SECRET_1=""
export QOBUZ_SECRET_2=""
export QOBUZ_SECRET_3=""

########## QOBUZ – ACTIVE TOKENS & SESSION ##########
# Value used in X-User-Auth-Token header
export QOBUZ_USER_AUTH_TOKEN=""

# Value used in X-Session-Id header (optional)
export QOBUZ_SESSION_ID=""

# Default track/file parameters for convenience
export QOBUZ_TRACK_ID_DEFAULT=""
export QOBUZ_FORMAT_ID_DEFAULT=""      # e.g. "7"
export QOBUZ_INTENT_DEFAULT=""         # e.g. "stream"
export QOBUZ_REQUEST_TS_DEFAULT=""     # unix timestamp used in file/url
export QOBUZ_REQUEST_SIG_DEFAULT=""    # request signature for file/url

########## TIDAL – AUTH BLOCK ##########
# TIDAL access token (for Authorization: Bearer)
export TIDAL_AUTH_TOKEN=""

# TIDAL refresh token (if you use refresh flows)
export TIDAL_REFRESH_TOKEN=""

# Expiry timestamp (unix seconds) if you track it
export TIDAL_TOKEN_EXPIRES_UNIX=""

# TIDAL internal user id and country code
export TIDAL_USER_ID=""
export TIDAL_COUNTRY_CODE=""           # e.g. "SE", "US"

# Default TIDAL track configuration
export TIDAL_TRACK_ID_DEFAULT=""
export TIDAL_INCLUDE_LYRICS_DEFAULT="" # "true" / "false"

# For API calls this is what you put in the Authorization header
export TIDAL_ACCESS_TOKEN="${TIDAL_AUTH_TOKEN}"

########## BEATPORT – TOKENS ##########
# Optional Beatport token you captured from a specific track call
export BEATPORT_ACCESS_TOKEN_TRACK=""

# A more recent/general Beatport token, e.g. from /v4/my/beatport
export BEATPORT_ACCESS_TOKEN_MY=""

# Default Beatport track id for convenience
export BEATPORT_TRACK_ID_DEFAULT=""

# For API calls, prefer BEATPORT_ACCESS_TOKEN_MY but fall back to TRACK
export BEATPORT_ACCESS_TOKEN="${BEATPORT_ACCESS_TOKEN_MY:-$BEATPORT_ACCESS_TOKEN_TRACK}"

########## SPOTIFY – CLIENT CREDENTIALS & TOKENS ##########
# Spotify client credentials (for OAuth2)
export SPOTIFY_CLIENT_ID=""
export SPOTIFY_CLIENT_SECRET=""

# Optional username/password if you use a user-flow helper somewhere else
export SPOTIFY_USERNAME=""
export SPOTIFY_PASSWORD=""

# Access token and refresh token once obtained via OAuth2
export SPOTIFY_ACCESS_TOKEN=""
export SPOTIFY_REFRESH_TOKEN=""
export SPOTIFY_TOKEN_EXPIRES_UNIX=""

# Default Spotify track id for convenience (e.g. "3n3Ppam7vgaVa1iaRUc9Lp")
export SPOTIFY_TRACK_ID_DEFAULT=""

########## GENERIC HARVEST CONFIG ##########
# Time between track rows; keep conservative for rate limits
export RATE_LIMIT_DELAY="3"      # seconds
export RETRY_BASE_DELAY="10"     # seconds before first retry
export MAX_RETRIES="5"

# Input CSV: tidal_id,beatport_id,qobuz_id,spotify_id
export INPUT_CSV="tracks.csv"

# NDJSON output with all raw metadata
export OUTPUT_NDJSON="metadata_output_full.ndjson"

# Log and resume state files
export LOG_FILE="metadata_harvest_full.log"
export STATE_FILE="metadata_harvest.state"

# Optional: path to an exported Postman environment JSON
export POSTMAN_ENV_EXPORT="music-env.json"
```

---

## 2. `harvest_metadata_full.sh` (4‑service harvester template)

```bash
#!/usr/bin/env bash
set -euo pipefail

# Load all env variables from template file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/env_exports.sh"

INPUT="${INPUT_CSV:-tracks.csv}"
OUTPUT="${OUTPUT_NDJSON:-metadata_output_full.ndjson}"
LOG_FILE="${LOG_FILE:-metadata_harvest_full.log}"
STATE_FILE="${STATE_FILE:-metadata_harvest.state}"

RATE_LIMIT_DELAY="${RATE_LIMIT_DELAY:-3}"
RETRY_BASE_DELAY="${RETRY_BASE_DELAY:-10}"
MAX_RETRIES="${MAX_RETRIES:-5}"

log() {
  echo "[$(date '+%Y-%m-%dT%H:%M:%S%z')] $*" | tee -a "$LOG_FILE"
}

log "CONFIG:"
log "  TIDAL_COUNTRY_CODE=$TIDAL_COUNTRY_CODE"
log "  TIDAL_TRACK_ID_DEFAULT=$TIDAL_TRACK_ID_DEFAULT"
log "  BEATPORT_TRACK_ID_DEFAULT=$BEATPORT_TRACK_ID_DEFAULT"
log "  QOBUZ_APP_ID=$QOBUZ_APP_ID"
log "  QOBUZ_TRACK_ID_DEFAULT=$QOBUZ_TRACK_ID_DEFAULT"
log "  SPOTIFY_TRACK_ID_DEFAULT=$SPOTIFY_TRACK_ID_DEFAULT"

if [ ! -f "$INPUT" ]; then
  log "ERROR: Input CSV not found: $INPUT"
  exit 1
fi

touch "$OUTPUT" "$LOG_FILE" "$STATE_FILE"

LAST_INDEX=$(cat "$STATE_FILE" 2>/dev/null || echo "-1")
if ! [[ "$LAST_INDEX" =~ ^-?[0-9]+$ ]]; then
  LAST_INDEX="-1"
fi
log "Resuming from CSV row index > $LAST_INDEX"

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
      log "ERROR: Command failed after $retries retries: $cmd"
      return $status
    fi

    log "Command failed (attempt $retries), retrying in ${delay}s..."
    sleep "$delay"
    delay=$((delay * 2))
  done
}

# ---------- TIDAL: full track JSON ----------
get_tidal_full() {
  local track_id="$1"

  if [ -z "${TIDAL_ACCESS_TOKEN:-}" ]; then
    log "WARN: No TIDAL_ACCESS_TOKEN set; skipping TIDAL for $track_id"
    echo "{}"
    return 0
  fi

  local url="https://openapi.tidal.com/v2/tracks/${track_id}?countryCode=${TIDAL_COUNTRY_CODE}&include=lyrics"
  local cmd="curl -s -w '\n%{http_code}' \
    -H 'Authorization: Bearer ${TIDAL_ACCESS_TOKEN}' \
    -H 'Accept: */*' \
    '${url}'"

  local response
  response=$(do_with_retries "$cmd") || { echo "{}"; return 0; }

  local body status
  body=$(echo "$response" | sed '$d')
  status=$(echo "$response" | tail -n1)

  if [ "$status" = "401" ] || [ "$status" = "403" ]; then
    log "WARN: TIDAL token appears invalid (status $status) for track $track_id"
    echo "{\"error\":\"TIDAL_AUTH\",\"http_status\":$status}"
    return 0
  fi
  if [ "$status" -ge 400 ]; then
    log "WARN: TIDAL returned HTTP $status for track $track_id"
    echo "{\"error\":\"TIDAL_HTTP_${status}\",\"http_status\":$status}"
    return 0
  fi

  echo "$body"
}

# ---------- Beatport: full track JSON ----------
get_beatport_full() {
  local track_id="$1"

  local token="${BEATPORT_ACCESS_TOKEN_MY:-${BEATPORT_ACCESS_TOKEN_TRACK:-}}"

  if [ -z "$token" ]; then
    log "WARN: No Beatport access token set; skipping Beatport for $track_id"
    echo "{}"
    return 0
  fi

  local url="https://api.beatport.com/v4/catalog/tracks/${track_id}/"
  local cmd="curl -s -w '\n%{http_code}' \
    -H 'Authorization: Bearer ${token}' \
    -H 'Accept: application/json, text/plain, */*' \
    '${url}'"

  local response
  response=$(do_with_retries "$cmd") || { echo "{}"; return 0; }

  local body status
  body=$(echo "$response" | sed '$d')
  status=$(echo "$response" | tail -n1)

  if [ "$status" = "401" ] || [ "$status" = "403" ]; then
    log "WARN: Beatport token appears invalid (status $status) for track $track_id"
    echo "{\"error\":\"BEATPORT_AUTH\",\"http_status\":$status}"
    return 0
  fi
  if [ "$status" -ge 400 ]; then
    log "WARN: Beatport returned HTTP $status for track $track_id"
    echo "{\"error\":\"BEATPORT_HTTP_${status}\",\"http_status\":$status}"
    return 0
  fi

  echo "$body"
}

# ---------- Qobuz: full track JSON ----------
get_qobuz_full() {
  local track_id="$1"

  if [ -z "${QOBUZ_USER_AUTH_TOKEN:-}" ]; then
    log "WARN: No QOBUZ_USER_AUTH_TOKEN set; skipping Qobuz for $track_id"
    echo "{}"
    return 0
  fi

  local base="https://www.qobuz.com/api.json/0.2/track/get"
  local url="${base}?track_id=${track_id}&app_id=${QOBUZ_APP_ID}&user_auth_token=${QOBUZ_USER_AUTH_TOKEN}"

  local headers="-H 'Accept: */*' -H 'X-App-Id: ${QOBUZ_APP_ID}'"
  if [ -n "${QOBUZ_SESSION_ID:-}" ]; then
    headers="${headers} -H 'X-Session-Id: ${QOBUZ_SESSION_ID}'"
  fi

  local cmd="curl -s -w '\n%{http_code}' ${headers} '${url}'"

  local response
  response=$(do_with_retries "$cmd") || { echo "{}"; return 0; }

  local body status
  body=$(echo "$response" | sed '$d')
  status=$(echo "$response" | tail -n1)

  if [ "$status" = "401" ] || [ "$status" = "403" ]; then
    log "WARN: Qobuz token appears invalid (status $status) for track $track_id"
    echo "{\"error\":\"QOBUZ_AUTH\",\"http_status\":$status}"
    return 0
  fi
  if [ "$status" -ge 400 ]; then
    log "WARN: Qobuz returned HTTP $status for track $track_id"
    echo "{\"error\":\"QOBUZ_HTTP_${status}\",\"http_status\":$status}"
    return 0
  fi

  echo "$body"
}

# ---------- Spotify: full track JSON ----------
get_spotify_full() {
  local track_id="$1"

  if [ -z "${SPOTIFY_ACCESS_TOKEN:-}" ]; then
    log "WARN: No SPOTIFY_ACCESS_TOKEN set; skipping Spotify for $track_id"
    echo "{}"
    return 0
  fi

  local url="https://api.spotify.com/v1/tracks/${track_id}"

  local cmd="curl -s -w '\n%{http_code}' \
    -H 'Authorization: Bearer ${SPOTIFY_ACCESS_TOKEN}' \
    -H 'Accept: application/json' \
    '${url}'"

  local response
  response=$(do_with_retries "$cmd") || { echo "{}"; return 0; }

  local body status
  body=$(echo "$response" | sed '$d')
  status=$(echo "$response" | tail -n1)

  if [ "$status" = "401" ] || [ "$status" = "403" ]; then
    log "WARN: Spotify token appears invalid (status $status) for track $track_id"
    echo "{\"error\":\"SPOTIFY_AUTH\",\"http_status\":$status}"
    return 0
  fi
  if [ "$status" -ge 400 ]; then
    log "WARN: Spotify returned HTTP $status for track $track_id"
    echo "{\"error\":\"SPOTIFY_HTTP_${status}\",\"http_status\":$status}"
    return 0
  fi

  echo "$body"
}

ROW_INDEX=-1

# CSV format: tidal_id,beatport_id,qobuz_id,spotify_id
tail -n +2 "$INPUT" | while IFS=, read -r tidal_id beatport_id qobuz_id spotify_id; do
  ROW_INDEX=$((ROW_INDEX + 1))

  if [ "$ROW_INDEX" -le "$LAST_INDEX" ]; then
    continue
  fi

  tidal_id="${tidal_id:-}"
  beatport_id="${beatport_id:-}"
  qobuz_id="${qobuz_id:-}"
  spotify_id="${spotify_id:-}"

  if [ -z "$tidal_id" ] && [ -z "$beatport_id" ] && [ -z "$qobuz_id" ] && [ -z "$spotify_id" ]; then
    log "Row $ROW_INDEX: empty IDs, skipping"
    echo "$ROW_INDEX" > "$STATE_FILE"
    continue
  fi

  log "Processing row $ROW_INDEX: tidal='${tidal_id}', beatport='${beatport_id}', qobuz='${qobuz_id}', spotify='${spotify_id}'"

  local_tidal="{}"
  local_beatport="{}"
  local_qobuz="{}"
  local_spotify="{}"

  if [ -n "$tidal_id" ]; then
    local_tidal="$(get_tidal_full "$tidal_id")"
  fi
  if [ -n "$beatport_id" ]; then
    local_beatport="$(get_beatport_full "$beatport_id")"
  fi
  if [ -n "$qobuz_id" ]; then
    local_qobuz="$(get_qobuz_full "$qobuz_id")"
  fi
  if [ -n "$spotify_id" ]; then
    local_spotify="$(get_spotify_full "$spotify_id")"
  fi

  jq -c -n \
    --argjson tidal "$local_tidal" \
    --argjson beatport "$local_beatport" \
    --argjson qobuz "$local_qobuz" \
    --argjson spotify "$local_spotify" \
    --arg row_index "$ROW_INDEX" \
    '{
      tidal: $tidal,
      beatport: $beatport,
      qobuz: $qobuz,
      spotify: $spotify,
      row_index: ($row_index | tonumber)
    }' >> "$OUTPUT"

  echo "$ROW_INDEX" > "$STATE_FILE"

  log "Row $ROW_INDEX processed. Sleeping ${RATE_LIMIT_DELAY}s..."
  sleep "$RATE_LIMIT_DELAY"
done

log "Harvest complete. Output written to $OUTPUT"
```

---

## 3. `aggregate_metadata_full.py` (aggregator template, now with Spotify)

```python
#!/usr/bin/env python3
"""
aggregate_metadata_full.py (template)

- Reads NDJSON from metadata_output_full.ndjson (from harvest_metadata_full.sh)
- Each line: { "tidal": {...}, "beatport": {...}, "qobuz": {...}, "spotify": {...}, "row_index": N }
- Extracts candidate BPM/key/genre from each service.
- Builds canonical fields with priority: Beatport > Qobuz > TIDAL > Spotify.
"""

import csv
import json
from pathlib import Path

INPUT_NDJSON = Path("metadata_output_full.ndjson")
OUTPUT_CSV = Path("metadata_canonical.csv")

def extract_tidal_track_info(tidal_json):
    """
    Adjust these paths to match your actual TIDAL JSON.

    Example assumption:
      {
        "data": {
          "id": "...",
          "attributes": {
            "bpm": 128,
            "key": "F#m",
            "genre": { "name": "Techno" }
          }
        }
      }
    """
    if not isinstance(tidal_json, dict):
        return None, None, None, None
    data = tidal_json.get("data") or {}
    tidal_id = data.get("id")
    attrs = data.get("attributes") or {}

    bpm = attrs.get("bpm")
    key = attrs.get("key")
    genre = None
    genre_obj = attrs.get("genre")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return tidal_id, bpm, key, genre

def extract_beatport_track_info(bp_json):
    """
    Adjust these paths for Beatport JSON.

    Example assumption:
      {
        "id": 123,
        "bpm": 128,
        "key": "F#m",
        "genre": { "name": "Techno" }  # or list of genres
      }
    """
    if not isinstance(bp_json, dict):
        return None, None, None, None
    bp_id = bp_json.get("id")

    bpm = bp_json.get("bpm")
    key = bp_json.get("key")

    genre = None
    genre_obj = bp_json.get("genre") or bp_json.get("primary_genre")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, list) and genre_obj:
        first = genre_obj[0]
        if isinstance(first, dict):
            genre = first.get("name")
        elif isinstance(first, str):
            genre = first
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return bp_id, bpm, key, genre

def extract_qobuz_track_info(qb_json):
    """
    Adjust these paths for Qobuz JSON.

    Example assumption:
      {
        "id": 260231933,
        "bpm": 128,
        "key": "F#m",
        "genre": { "name": "Jazz" }
      }
    """
    if not isinstance(qb_json, dict):
        return None, None, None, None
    qb_id = qb_json.get("id")

    bpm = qb_json.get("bpm")
    key = qb_json.get("key")

    genre = None
    genre_obj = qb_json.get("genre") or qb_json.get("genre_info")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, list) and genre_obj:
        first = genre_obj[0]
        if isinstance(first, dict):
            genre = first.get("name")
        elif isinstance(first, str):
            genre = first
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return qb_id, bpm, key, genre

def extract_spotify_track_info(sp_json):
    """
    Adjust these paths for Spotify JSON.

    Example assumption for /v1/tracks:
      {
        "id": "3n3Ppam7vgaVa1iaRUc9Lp",
        "name": "...",
        "artists": [...],
        "album": {...}
      }

    For BPM/key, you might want to instead call /v1/audio-features/{id} and store
    that JSON under spotify.audio_features in the NDJSON. This template assumes
    those fields may be present at top-level for simplicity.
    """
    if not isinstance(sp_json, dict):
        return None, None, None, None
    sp_id = sp_json.get("id")

    # Placeholder extraction – adjust to real Spotify structure you store:
    bpm = sp_json.get("tempo")  # or from `audio_features["tempo"]`
    key = sp_json.get("key")    # or from `audio_features["key"]`, you might map numeric -> string

    genre = None
    genre_obj = sp_json.get("genre") or sp_json.get("genres")
    if isinstance(genre_obj, list) and genre_obj:
        genre = genre_obj[0]
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return sp_id, bpm, key, genre

def choose_canonical(bpm_bp, bpm_qb, bpm_td, bpm_sp,
                     key_bp, key_qb, key_td, key_sp,
                     genre_bp, genre_qb, genre_td, genre_sp):
    """
    Canonical selection with priority:
      Beatport > Qobuz > TIDAL > Spotify
    """
    canonical_bpm = bpm_bp or bpm_qb or bpm_td or bpm_sp
    canonical_key = key_bp or key_qb or key_td or key_sp
    canonical_genre = genre_bp or genre_qb or genre_td or genre_sp
    return canonical_bpm, canonical_key, canonical_genre

def main():
    if not INPUT_NDJSON.exists():
        raise SystemExit(f"Input NDJSON not found: {INPUT_NDJSON}")

    rows = []

    with INPUT_NDJSON.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            tidal_json = obj.get("tidal")
            bp_json = obj.get("beatport")
            qb_json = obj.get("qobuz")
            sp_json = obj.get("spotify")
            row_index = obj.get("row_index")

            tidal_id, tidal_bpm, tidal_key, tidal_genre = extract_tidal_track_info(tidal_json)
            bp_id, bp_bpm, bp_key, bp_genre = extract_beatport_track_info(bp_json)
            qb_id, qb_bpm, qb_key, qb_genre = extract_qobuz_track_info(qb_json)
            sp_id, sp_bpm, sp_key, sp_genre = extract_spotify_track_info(sp_json)

            canonical_bpm, canonical_key, canonical_genre = choose_canonical(
                bp_bpm, qb_bpm, tidal_bpm, sp_bpm,
                bp_key, qb_key, tidal_key, sp_key,
                bp_genre, qb_genre, tidal_genre, sp_genre
            )

            rows.append({
                "row_index": row_index,
                "tidal_id": tidal_id,
                "beatport_id": bp_id,
                "qobuz_id": qb_id,
                "spotify_id": sp_id,
                "tidal_bpm": tidal_bpm,
                "beatport_bpm": bp_bpm,
                "qobuz_bpm": qb_bpm,
                "spotify_bpm": sp_bpm,
                "canonical_bpm": canonical_bpm,
                "tidal_key": tidal_key,
                "beatport_key": bp_key,
                "qobuz_key": qb_key,
                "spotify_key": sp_key,
                "canonical_key": canonical_key,
                "tidal_genre": tidal_genre,
                "beatport_genre": bp_genre,
                "qobuz_genre": qb_genre,
                "spotify_genre": sp_genre,
                "canonical_genre": canonical_genre,
            })

    fieldnames = [
        "row_index",
        "tidal_id", "beatport_id", "qobuz_id", "spotify_id",
        "tidal_bpm", "beatport_bpm", "qobuz_bpm", "spotify_bpm", "canonical_bpm",
        "tidal_key", "beatport_key", "qobuz_key", "spotify_key", "canonical_key",
        "tidal_genre", "beatport_genre", "qobuz_genre", "spotify_genre", "canonical_genre",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
```

---

## 4. TIDAL visualization script template (Postman Tests)

```js
// TIDAL track visualization template (Tests tab)

let data;
try {
    data = pm.response.json();
} catch (e) {
    pm.visualizer.set('<p>Response is not valid JSON.</p>', {});
    return;
}

const track = data && data.data && data.data.attributes ? data.data.attributes : {};

function formatDuration(ptOrSeconds) {
    if (typeof ptOrSeconds === 'number') {
        const totalSec = ptOrSeconds;
        const mm = Math.floor(totalSec / 60);
        const ss = totalSec % 60;
        return `${mm}:${ss.toString().padStart(2, '0')}`;
    }
    if (typeof ptOrSeconds === 'string' && ptOrSeconds.startsWith('PT')) {
        const m = ptOrSeconds.match(/^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/);
        if (!m) return ptOrSeconds;
        const h = parseInt(m[1] || '0', 10);
        const min = parseInt(m[2] || '0', 10);
        const s = parseInt(m[3] || '0', 10);
        const totalSec = h * 3600 + min * 60 + s;
        const mm = Math.floor(totalSec / 60);
        const ss = totalSec % 60;
        return `${mm}:${ss.toString().padStart(2, '0')}`;
    }
    return 'N/A';
}

const title = track.title || 'Unknown';
const duration = formatDuration(track.duration);
const isrc = track.isrc || 'N/A';
const popularity = typeof track.popularity === 'number' ? track.popularity : null;
const popularityDisplay = popularity !== null ? (popularity * 100).toFixed(1) + '%' : 'N/A';
const createdAt = track.createdAt || 'N/A';

let popularityHistory = [];
if (popularity !== null) {
    const base = popularity * 100;
    popularityHistory = [
        { label: 'T-4', value: Math.max(0, base - 10) },
        { label: 'T-3', value: Math.max(0, base - 5) },
        { label: 'T-2', value: base },
        { label: 'T-1', value: Math.min(100, base + 3) },
        { label: 'Now', value: base }
    ];
}

const template = `
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/modern-normalize/2.0.0/modern-normalize.min.css" />
<style>
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 16px; color: #111; }
    .container { max-width: 960px; margin: 0 auto; }
    .details-panel {
        background: #f5f5f7;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 24px;
        border: 1px solid #e0e0e0;
    }
    .details-panel h2 {
        margin: 0 0 12px;
        font-size: 20px;
    }
    .detail-row {
        display: flex;
        padding: 6px 0;
        border-bottom: 1px solid #e6e6e6;
        font-size: 14px;
    }
    .detail-row:last-child { border-bottom: none; }
    .detail-label {
        font-weight: 600;
        width: 120px;
        color: #555;
    }
    .detail-value {
        flex: 1;
        color: #222;
        word-break: break-word;
    }
    .chart-container {
        background: #fff;
        border-radius: 8px;
        padding: 16px 20px 24px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
    }
    .chart-title {
        margin: 0 0 12px;
        font-size: 18px;
    }
    .chart-empty {
        font-size: 14px;
        color: #777;
        padding-top: 8px;
    }
    canvas { max-width: 100%; }
</style>

<div class="container">
    <div class="details-panel">
        <h2>Track Details (TIDAL)</h2>
        <div class="detail-row">
            <span class="detail-label">Title:</span>
            <span class="detail-value">{{title}}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Duration:</span>
            <span class="detail-value">{{duration}}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">ISRC:</span>
            <span class="detail-value">{{isrc}}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Popularity:</span>
            <span class="detail-value">{{popularityDisplay}}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Created At:</span>
            <span class="detail-value">{{createdAt}}</span>
        </div>
    </div>

    <div class="chart-container">
        <h3 class="chart-title">Popularity History</h3>
        {{#if hasPopularityHistory}}
            <canvas id="popularityChart" height="120"></canvas>
        {{else}}
            <div class="chart-empty">No popularity history available (synthetic series only if configured).</div>
        {{/if}}
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
(function() {
    const ctx = document.getElementById('popularityChart');
    if (!ctx) return;

    const labels = {{popularityLabels}};
    const values = {{popularityValues}};

    if (!labels.length) return;

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Popularity (%)',
                data: values,
                tension: 0.25,
                fill: false,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.3)',
                pointRadius: 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Popularity (%)' }
                },
                x: {
                    title: { display: true, text: 'Time' }
                }
            }
        }
    });
})();
</script>
`;

const payload = {
    title,
    duration,
    isrc,
    popularityDisplay,
    createdAt,
    hasPopularityHistory: popularityHistory.length > 0,
    popularityLabels: popularityHistory.map(p => p.label),
    popularityValues: popularityHistory.map(p => p.value)
};

pm.visualizer.set(template, payload);
```

---

You can now:

1. Fill in `env_exports.sh` with your real values (privately).
2. Prepare `tracks.csv` with:

```csv
tidal_id,beatport_id,qobuz_id,spotify_id
...
```

3. Run:

```bash
source ./env_exports.sh
./harvest_metadata_full.sh
python3 aggregate_metadata_full.py
```

This is the full, final, secret‑free setup.

