Below is a concrete, practical setup that:

- Uses **real test creds** (your Spotify client id/secret)  
- Fetches as much metadata as is reasonably accessible via public/web APIs  
- Is designed so you can extend it to lyrics + PDF companions where the service exposes them  
- Gives you **bash export commands** so you can set up your environment quickly

Because fetching lyrics and PDF booklets is highly service‑specific (and often restricted / DRMed), I’ll show:

1. How to wire the dynamic Postman collection (high‑level, building on what we already discussed)  
2. What you can **actually** fetch per service via API (including lyrics/booklets where available)  
3. A metadata aggregation step in Tests that produces a **summary object** of all tags  
4. Concrete **bash export commands** for environment variables, including your provided Spotify creds  
5. Example **bash + Postman CLI** commands to batch-fetch metadata

---

## 1. Core idea: multi-service metadata + summary

For each track/lookup you will:

- Use `REQUEST_INPUT` → parse into `PARSED_SERVICE / PARSED_QUERY_TYPE / PARSED_QUERY_VALUE` as before.
- Hit whichever of these you have creds for:
  - Beatport (catalog)  
  - Tidal (openapi + web search)  
  - Spotify (Web API)  
  - Apple Music (catalog) and/or iTunes Search  
  - Qobuz (web API)  
- In each request’s **Tests**, normalize key tags into a common structure and store them in environment variables:
  - `AGGREGATED_METADATA` → JSON object keyed by service name
  - Each sub-object includes: title, artists, album, duration_ms, isrc, album_art_url, release_date, explicit flag, plus extras:
    - `lyrics` (or `lyrics_excerpt` if only partial)
    - `pdf_companion_urls` (where any booklet/liner notes links are visible in metadata)
- After running all services (e.g., via a collection run), you have a single aggregated block with all tags.

I’ll show the summary builder in Section 3.

---

## 2. What you can realistically fetch (including lyrics / PDFs)

### Spotify

Public Web API:

- Full track metadata including:
  - `name`, `artists`, `album.name`, `duration_ms`, `explicit`, `external_ids.isrc`, `album.images`, `popularity`, etc.
- **No full lyrics** via official API.  
  - Spotify’s lyrics in the web player are served via non-public endpoints and lyrics providers (DRM / licensing). You can sometimes reverse-engineer web calls (like `gae2-spclient.spotify.com/...`), but those are not stable or officially supported.
- No PDF booklet via public API.

Conclusion: For Spotify, your best bet is full metadata + maybe **short preview** from web-only lyrics/notes endpoints if you’re OK with brittle, undocumented APIs. But in a “clean” Postman collection, assume: **no lyrics, no PDFs** via official API.

---

### Tidal

- `openapi.tidal.com/v2/tracks/{id}` and related endpoints can return:
  - Title, artists, album, `duration`, `isrc`, album art, etc.
- Lyrics:
  - There are lyrics endpoints in Tidal’s internal/web API, but not in the public OpenAPI spec for general client use.
- PDF/Booklets:
  - Some releases (especially classical) may expose booklet/notes URLs in “extras” or album metadata fields. If present, you can parse them as `pdf_companion_urls`.

So: **metadata + maybe booklet URLs** if they appear in the JSON.

---

### Apple Music / iTunes

Apple Music catalog:

- `attributes` can include:
  - `name`, `artistName`, `albumName`, `durationInMillis`, `isrc`, `artwork`, `releaseDate`, `playParams`, etc.
- Lyrics:
  - Apple Music has lyrics endpoints (e.g. those `lyrics-excerpt` or `syllable-lyrics` endpoints like in your `apple` collection), but they are **private**, require specific app auth context, and often content protection.
- PDF companions:
  - Some classical Apple Music releases (especially digital booklets) may have assets that are accessible via album metadata or “more by artist” sections.

iTunes:

- Don’t generally expose lyrics or booklets; just metadata.

Conclusion: you can **scrape booklet/companion URLs if they appear** in album-level metadata, but not reliably via official APIs.

---

### Qobuz

- Web API (what you have in `qob` collection):
  - `track/get`, `album/get` can return:
    - Detailed track/album metadata, `duration`, `isrc`, hi-res flags, covers, sometimes multi-disc structure.
- Lyrics:
  - Lyrics presence is limited; some releases embed excerpt/lyrics fields, most do not.
- PDF companions:
  - Qobuz often offers **digital booklets (PDF)** as separate files. Those usually appear in `album/get` responses under some “digital booklet” asset list or `booklet_url`/`pdf` field.

So: Qobuz is one of the better sources for **PDF companions**. In Postman, you can:

- Use `track/get` to find the album id from a track  
- Then call `album/get` to look for fields like `digital_booklet`, `booklet_url`, or `pdf_url` and collect them.

---

### Beatport

- Mainly full metadata (titles, artists, labels, genres, BPM, key, etc.).
- No lyrics.
- No PDF.

---

Given these realities, “fetch all metadata including lyrics and pdf companions” means:

- **All classical tags** from each main service.
- **Lyrics / excerpt** only where APIs expose them (Apple Music/Tidal web endpoints, Qobuz if available).
- **PDF/booklets** primarily from Qobuz (and sometimes Apple Music), based on album metadata.

---

## 3. Aggregated metadata builder (Tests script)

Add this in the **collection Tests** so every service request contributes to one big `AGGREGATED_METADATA` object.

```javascript
// === Aggregated Metadata Collector ===

let raw;
try {
  raw = pm.response.json();
} catch (e) {
  console.warn("Response not JSON; skipping aggregation");
  return;
}

const service = pm.environment.get("PARSED_SERVICE") || "unknown";

// Load existing aggregated metadata
let agg = {};
try {
  const existing = pm.environment.get("AGGREGATED_METADATA");
  agg = existing ? JSON.parse(existing) : {};
} catch (e) {
  agg = {};
}

// Base structure we will fill per service
const record = {
  service,
  title: null,
  artists: [],
  album: null,
  duration_ms: null,
  isrc: null,
  release_date: null,
  explicit: null,
  album_art_url: null,
  // Extended fields:
  lyrics: null,
  lyrics_excerpt: null,
  pdf_companion_urls: [],   // e.g., booklets
  raw: raw                  // optional: full raw payload
};

// Service-specific extractors:

if (service === "spotify") {
  let t = null;
  if (raw.duration_ms !== undefined) {
    t = raw;
  } else if (raw.tracks?.items?.length) {
    t = raw.tracks.items[0];
  }

  if (t) {
    record.title = t.name || null;
    record.artists = (t.artists || []).map(a => a.name).filter(Boolean);
    record.album = t.album?.name || null;
    record.duration_ms = t.duration_ms || null;
    record.explicit = t.explicit ?? null;
    record.release_date = t.album?.release_date || null;
    record.album_art_url = t.album?.images?.[0]?.url || null;
    record.isrc = t.external_ids?.isrc || null;
  }

  // No official lyrics/booklet from Spotify Web API
}

if (service === "beatport") {
  let tr = null;
  if (raw.length_ms !== undefined) {
    tr = raw;
  } else if (raw.results?.length) {
    tr = raw.results[0];
  }
  if (tr) {
    record.title = tr.name || tr.title || null;
    record.artists = (tr.artists || tr.producers || []).map(a => a.name).filter(Boolean);
    record.album = tr.release?.name || null;
    record.duration_ms = tr.length_ms || null;
    record.isrc = tr.isrc || null;
    record.release_date = tr.release_date || null;
    record.explicit = null; // Beatport doesn't use explicit flag like streaming services
    record.album_art_url = tr.images?.large || tr.images?.medium || null;
  }
}

if (service === "tidal") {
  // Try openapi v2 track or generic search
  let tr = null;

  if (raw.title && raw.duration !== undefined) {
    tr = raw;
  } else if (raw.items?.length && raw.items[0].item) {
    tr = raw.items[0].item;
  } else if (raw.data?.length && raw.data[0].attributes) {
    tr = raw.data[0].attributes;
  }

  if (tr) {
    record.title = tr.title || tr.name || null;
    record.artists = (tr.artists || tr.artist?.name ? [tr.artist.name] : []).map(a => (typeof a === "string" ? a : a.name)).filter(Boolean);
    record.album = tr.album?.title || tr.albumTitle || null;
    record.duration_ms = (tr.duration ? tr.duration * 1000 : null);
    record.isrc = tr.isrc || tr.externalIds?.isrc || null;
    record.release_date = tr.streamStartDate || tr.releaseDate || null;
    record.album_art_url = tr.album?.cover || tr.image || null;
  }

  // If lyrics snippet present anywhere (non-standard)
  if (raw.lyrics?.lines) {
    record.lyrics_excerpt = raw.lyrics.lines.map(l => l.words).join(" ");
  }
}

if (service === "apple") {
  // Apple Music catalog
  let tr = null;
  if (raw.data?.length && raw.data[0].attributes) {
    tr = raw.data[0].attributes;
  } else if (raw.results?.songs?.data?.length && raw.results.songs.data[0].attributes) {
    tr = raw.results.songs.data[0].attributes;
  }

  if (tr) {
    record.title = tr.name || null;
    record.artists = [tr.artistName].filter(Boolean);
    record.album = tr.albumName || null;
    record.duration_ms = tr.durationInMillis || null;
    record.isrc = tr.isrc || null;
    record.explicit = tr.contentRating === "explicit";
    record.release_date = tr.releaseDate || null;
    if (tr.artwork?.url) {
      record.album_art_url = tr.artwork.url
        .replace("{w}", "600")
        .replace("{h}", "600");
    }
    // lyrics + pdf would need extra calls to private endpoints; if you call them, parse into record.lyrics / pdf_companion_urls
  }
}

if (service === "itunes") {
  if (Array.isArray(raw.results) && raw.results[0]) {
    const tr = raw.results[0];
    record.title = tr.trackName || null;
    record.artists = [tr.artistName].filter(Boolean);
    record.album = tr.collectionName || null;
    record.duration_ms = tr.trackTimeMillis || null;
    record.isrc = tr.isrc || null; // some iTunes results expose ISRC
    record.release_date = tr.releaseDate || null;
    record.album_art_url = tr.artworkUrl100 || tr.artworkUrl60 || null;
  }
}

if (service === "qobuz") {
  let tr = null;
  if (raw.duration !== undefined && raw.title) {
    tr = raw;
  } else if (Array.isArray(raw.tracks) && raw.tracks[0]) {
    tr = raw.tracks[0];
  }

  if (tr) {
    record.title = tr.title || null;
    record.artists = [tr.performer?.name || tr.artist?.name].filter(Boolean);
    record.album = tr.album?.title || null;
    record.duration_ms = tr.duration ? tr.duration * 1000 : null;
    record.isrc = tr.isrc || null;
    record.release_date = tr.release_date || tr.album?.release_date || null;
    record.album_art_url = tr.image?.large || tr.image?.thumbnail || null;
  }

  // If you also call album/get, parse PDF companion URLs there:
  if (raw.digital_booklet_url) {
    record.pdf_companion_urls.push(raw.digital_booklet_url);
  }
  if (raw.album?.booklet_url) {
    record.pdf_companion_urls.push(raw.album.booklet_url);
  }
}

// Put/replace under its service key
agg[service] = record;

// Persist back
pm.environment.set("AGGREGATED_METADATA", JSON.stringify(agg, null, 2));

pm.test(`Aggregated metadata updated for ${service}`, () => {
  pm.expect(agg[service]).to.be.an("object");
});
```

After running several service requests for a single `REQUEST_INPUT`, you’ll have:

```json
{
  "spotify": { ... },
  "beatport": { ... },
  "tidal": { ... },
  "apple": { ... },
  "itunes": { ... },
  "qobuz": { ... }
}
```

in `AGGREGATED_METADATA`.

---

## 4. Bash export commands (with your real Spotify vars)

### 4.1 Environment exports (for your shell / scripts)

```bash
# Core input
export REQUEST_INPUT="USRC11702778"

# Spotify (from your message)
export SPOTIFY_CLIENT_ID="9d833039ed2743948b4fbbca824bc815"
export SPOTIFY_CLIENT_SECRET="91cceb8042624f2ea5c4420adbc28334"

# Optional: share a token / expiry if you cache it from Postman or from a script
export SPOTIFY_ACCESS_TOKEN=""
export SPOTIFY_TOKEN_EXPIRES_AT="0"

# Beatport
export BEATPORT_ACCESS_TOKEN="REPLACE_WITH_BEATPORT_TOKEN"

# Tidal
export TIDAL_AUTH_TOKEN="REPLACE_WITH_TIDAL_TOKEN"
export TIDAL_COUNTRY_CODE="US"

# Apple Music / iTunes
export APPLE_MUSIC_DEV_TOKEN="REPLACE_WITH_APPLE_MUSIC_DEV_JWT"
export APPLE_MUSIC_USER_TOKEN="REPLACE_WITH_APPLE_MUSIC_USER_TOKEN"   # optional
export ITUNES_COUNTRY_CODE="US"

# Qobuz
export QOBUZ_USER_AUTH_TOKEN="REPLACE_WITH_QOBUZ_USER_TOKEN"
export QOBUZ_APP_ID="REPLACE_WITH_QOBUZ_APP_ID"
```

If you’re **only testing Spotify** at first, the minimum is:

```bash
export REQUEST_INPUT="spotify Justin Timberlake Filthy"
export SPOTIFY_CLIENT_ID="9d833039ed2743948b4fbbca824bc815"
export SPOTIFY_CLIENT_SECRET="91cceb8042624f2ea5c4420adbc28334"
```

---

## 5. Bash + Postman CLI to batch-fetch metadata

Assuming:

- Your collection is saved as `dynamic-music-api.postman_collection.json`
- Your environment as `music-env.postman_environment.json`
- You installed Postman CLI (`npm install -g @postman/postman-cli`, or via docs)

### 5.1 Single query via CLI

```bash
# Example: ISRC across all services
export REQUEST_INPUT="USRC11702778"

postman collection run dynamic-music-api.postman_collection.json \
  --environment music-env.postman_environment.json \
  --iteration-data <(printf 'input_string\n%s\n' "$REQUEST_INPUT") \
  --reporters cli
```

In your collection-level pre-request you can sync `iterationData` to `REQUEST_INPUT`:

```javascript
const v = pm.iterationData.get("input_string");
if (v) pm.environment.set("REQUEST_INPUT", v);
```

### 5.2 Batch: local list of ISRCs or titles

Create `tracks.csv`:

```csv
input_string
USRC11702778
High Street
spotify 4cOdK2wGLETKBW3PvgPWqT
beatport 17606729
```

Run:

```bash
postman collection run dynamic-music-api.postman_collection.json \
  --environment music-env.postman_environment.json \
  --iteration-data tracks.csv \
  --reporters cli
```

Each iteration:

- Parser turns `input_string` into parsed service/type/value.
- You run the relevant service requests (or all of them).
- `AGGREGATED_METADATA` is updated, and you can export it via:
  - An extra “exporter” request that POSTs `AGGREGATED_METADATA` to your own local API / writes to a file.

---

If you’d like, next step I can:

- Focus only on **Spotify + Qobuz** and wire in more aggressive attempts to pull lyrics and booklets using known-but-undocumented web endpoints, or  
- Show you a **router request** that, for a single `REQUEST_INPUT`, uses `pm.sendRequest` internally to hit all 5 services and returns a single combined JSON object in one Postman response.