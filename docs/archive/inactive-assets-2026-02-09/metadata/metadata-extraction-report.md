# Metadata Retrieval Code Extraction Report

**Generated**: 2026-01-25
**Repositories Analyzed**: tagslut, sluttools, fla_cid, flaccid

---

## Executive Summary

| Repository | Status | APIs Implemented |
|------------|--------|------------------|
| **tagslut** | Production-ready | Spotify, Apple Music, Qobuz, Tidal, MusicBrainz |
| **flaccid** | Production-ready | Qobuz, Tidal, Apple Music, Beatport, Discogs, Genius, LyricsOvh |
| **fla_cid** | Archive/Reference | Qobuz, Tidal (active), Apple Music, Discogs, MusicBrainz (archive) |
| **sluttools** | No API integration | Local-only playlist matching |

---

## Table of Contents

1. [Spotify](#1-spotify)
2. [Apple Music / iTunes](#2-apple-music--itunes)
3. [Qobuz](#3-qobuz)
4. [Tidal](#4-tidal)
5. [MusicBrainz](#5-musicbrainz)
6. [Discogs](#6-discogs)
7. [Beatport](#7-beatport)
8. [Lyrics Providers](#8-lyrics-providers)
9. [Base Classes & Data Models](#9-base-classes--data-models)
10. [Cascade & Fallback Patterns](#10-cascade--fallback-patterns)
11. [Error Handling](#11-error-handling)
12. [File Download Utilities](#12-file-download-utilities)
13. [Configuration Management](#13-configuration-management)
14. [Duration/Length Retrieval](#14-durationlength-retrieval)
15. [Dependencies](#15-dependencies)
16. [API Endpoints Quick Reference](#16-api-endpoints-quick-reference)

---

## 1. Spotify

### Source: tagslut

**File**: `~/Projects/tagslut/src/tagslut/providers/spotify.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `base_url` | `https://api.spotify.com/v1` |
| `name` | `spotify` |

#### Authentication

- **Type**: Bearer token via async token getter callable
- **Header**: `Authorization: Bearer {token}`

#### Key Methods

```python
async def search_track(self, query: str, *, limit: int = 5) -> List[Track]
async def get_track(self, external_id: str) -> Track
async def get_album(self, external_id: str) -> Album
```

#### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search` | GET | Search tracks by query |
| `/tracks/{id}` | GET | Get single track metadata |
| `/albums/{id}` | GET | Get album metadata |

#### Metadata Extracted

- `title` (name)
- `artists` (array with id, name, external_urls)
- `album` (with images, release_date)
- `duration_ms` (milliseconds - direct)
- `track_number`, `disc_number`
- `explicit` (boolean)
- `isrc` (from external_ids)

#### Release Date Parsing

```python
def _parse_release_date(value: Optional[str]) -> Optional[datetime]:
    if len(value) == 4:          # Year only: "2023"
        return datetime.fromisoformat(f"{value}-01-01")
    if len(value) == 7:          # Year-Month: "2023-05"
        return datetime.fromisoformat(f"{value}-01")
    return datetime.fromisoformat(value)  # Full ISO: "2023-05-15"
```

#### Dependencies

- `httpx` (AsyncClient)
- `pydantic` (data models)

---

## 2. Apple Music / iTunes

### Source A: tagslut (Full Apple Music API)

**File**: `~/Projects/tagslut/src/tagslut/providers/apple_music.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `base_url` | `https://api.music.apple.com/v1` |
| `name` | `apple_music` |
| `storefront` | Default: `us` |

#### Authentication

- **Type**: JWT Bearer token (developer_token)
- **Header**: `Authorization: Bearer {developer_token}`

#### Key Methods

```python
async def search_track(self, query: str, *, limit: int = 5) -> List[Track]
async def get_track(self, external_id: str) -> Track
async def get_album(self, external_id: str) -> Album
```

#### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/catalog/{storefront}/search` | GET | Search songs |
| `/catalog/{storefront}/songs/{id}` | GET | Get song metadata |
| `/catalog/{storefront}/albums/{id}` | GET | Get album metadata |

#### Artwork URL Template

```python
# Apple returns template URLs like:
# https://example.mzstatic.com/image/thumb/{w}x{h}.jpg
url = url_template.replace("{w}", "600").replace("{h}", "600")
```

#### Metadata Extracted

- `title` (attributes.name)
- `artists` (comma-separated artistName)
- `album` (from relationships)
- `duration_ms` (durationInMillis - direct)
- `track_number`, `disc_number`
- `explicit` (contentRating == "explicit")
- `isrc`

---

### Source B: flaccid (iTunes Search API - No Auth)

**File**: `~/Projects/flaccid/src/flaccid/plugins/apple.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://itunes.apple.com/search` |
| Authentication | None required (public API) |

#### Key Features

- **ISRC Lookup**: Supported via `isrc` parameter
- **No Authentication**: Public iTunes Search API

#### Key Methods

```python
async def get_track(self, track_id: str | None = None, *, isrc: str | None = None) -> TrackMetadata
async def get_track_by_isrc(self, isrc: str) -> TrackMetadata
async def search_track(self, query: str | None = None, *, isrc: str | None = None) -> Any
async def fetch_cover_art(self, url: str) -> bytes | None
```

#### API Parameters

| Parameter | Description |
|-----------|-------------|
| `term` | Search query |
| `entity` | `song` or `album` |
| `country` | `us` (default) |
| `isrc` | ISRC code for direct lookup |
| `id` | Track/album ID |

#### Metadata Mapping

```python
TrackMetadata(
    title=track.get("trackName", ""),
    artist=track.get("artistName", ""),
    album=track.get("collectionName", ""),
    track_number=track.get("trackNumber"),
    disc_number=track.get("discNumber"),
    year=int(track["releaseDate"][:4]) if "releaseDate" in track else None,
    isrc=track.get("isrc"),
    art_url=track.get("artworkUrl100"),
    source="apple",
)
```

---

## 3. Qobuz

### Source A: tagslut (Metadata Only)

**File**: `~/Projects/tagslut/src/tagslut/providers/qobuz.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `base_url` | `https://www.qobuz.com/api.json/0.2` |
| `name` | `qobuz` |

#### Authentication

- **Type**: Query parameters
- **Required**: `app_id`, `app_secret`

#### Key Methods

```python
async def search_track(self, query: str, *, limit: int = 5) -> List[Track]
async def get_track(self, external_id: str) -> Track
async def get_album(self, external_id: str) -> Album
```

#### Duration Conversion

```python
# Qobuz returns duration in SECONDS
duration_ms = int(data.get("duration", 0)) * 1000 if data.get("duration") else None
```

#### Artwork Fallback Chain

```python
images = data.get("image") or {}
image_url = images.get("large") or images.get("medium") or images.get("small")
```

---

### Source B: flaccid (With Download + Signing)

**File**: `~/Projects/flaccid/src/flaccid/plugins/qobuz.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://www.qobuz.com/api.json/0.2/` |
| `_APP_SECRET` | Hardcoded: `abb21364945c0583309667d13ca3d93a` |

#### Authentication Flow

1. Load `app_id` from settings
2. Load `username`/`password` from keyring (`flaccid_qobuz`)
3. POST to `/user/login` with credentials
4. Receive and store `user_auth_token`

#### Request Signing Algorithm

```python
def _generate_signature(self, method_name: str, params: dict, timestamp: float) -> str:
    # Sort parameters alphabetically by key
    sorted_params = OrderedDict(sorted(params.items()))
    # Concatenate key+value pairs
    param_str = "".join([f"{k}{v}" for k, v in sorted_params.items()])
    # Remove slashes from method name
    method_name_cleaned = method_name.replace("/", "")
    # Build base string
    base_string = f"{method_name_cleaned}{param_str}{timestamp}{self._APP_SECRET}"
    # Return MD5 hash
    return hashlib.md5(base_string.encode()).hexdigest()
```

#### Download Quality Format IDs

| Format ID | Quality |
|-----------|---------|
| 5 | MP3 320kbps |
| 6 | FLAC 16-bit/44.1kHz (CD quality) |
| 7 | FLAC 24-bit/96kHz |
| 19 | FLAC 24-bit/96kHz (variant) |
| 27 | FLAC 24-bit/192kHz |
| 29 | FLAC 24-bit/192kHz (variant) |

#### Key Methods

```python
async def authenticate(self) -> None
async def get_track(self, track_id: str) -> TrackMetadata
async def download(self, track_id: str, dest: Path) -> bool
```

#### Signed Request Example

```python
file_url_data = await self._request(
    "track/getFileUrl",
    track_id=track_id,
    format_id=27,  # 24-bit/192kHz
    intent="stream",
    sign_request=True,  # Enables signature generation
)
```

---

## 4. Tidal

### Source A: tagslut (Token + Session ID)

**File**: `~/Projects/tagslut/src/tagslut/providers/tidal.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `base_url` | `https://api.tidalhifi.com/v1` |
| `name` | `tidal` |
| `country_code` | Default: `US` |

#### Authentication

- **Type**: Custom headers
- **Headers**:
  - `X-Tidal-Token: {token}`
  - `sessionId: {session_id}`

#### Duration Conversion

```python
# Tidal returns duration in SECONDS
duration_ms = int(data.get("duration", 0)) * 1000 if data.get("duration") else None
```

#### Artwork URL Construction

```python
image_id = data.get("cover")
if image_id:
    artwork_url = f"https://resources.tidal.com/images/{image_id}/640x640.jpg"
```

---

### Source B: flaccid (OAuth + Rate Limiting)

**File**: `~/Projects/flaccid/src/flaccid/plugins/tidal.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://api.tidalhifi.com/v1/` |
| `AUTH_URL` | `https://auth.tidal.com/v1/oauth2/token` |

#### OAuth Authentication Flow

```python
async def authenticate(self) -> None:
    # Try refresh token first
    refresh_token = keyring.get_password("flaccid_tidal", "refresh_token")
    if refresh_token:
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    else:
        # Fall back to username/password
        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }

    # POST to AUTH_URL
    # Store new access_token and refresh_token
```

#### Rate Limiting with Exponential Backoff

```python
async def _get_with_retry(self, url: str, **kwargs) -> aiohttp.ClientResponse:
    for attempt in range(5):
        resp = await self.session.get(url, **kwargs)
        if resp.status != 429:
            return resp

        # Honor Retry-After header or use exponential backoff
        retry_after = resp.headers.get("Retry-After")
        await resp.release()
        delay = float(retry_after) if retry_after else 2**attempt
        await asyncio.sleep(delay)

    return resp
```

#### Key Methods

```python
async def search_track(self, query: str) -> Any
async def get_track(self, track_id: str) -> TrackMetadata
async def get_album(self, album_id: str) -> AlbumMetadata
async def browse_album(self, album_id: str) -> list[TrackMetadata]
async def download_track(self, track_id: str, dest: Path) -> bool
async def download_playlist(self, playlist_id: str, dest_dir: Path) -> list[Path]
```

#### HLS Stream Download

```python
async def download_track(self, track_id: str, dest: Path) -> bool:
    data = await self._request(f"tracks/{track_id}/streamUrl")
    url = data.get("url")

    # Get HLS playlist
    async with await self._get_with_retry(url) as resp:
        playlist = await resp.text()

    # Parse segment URLs
    base = url.rsplit("/", 1)[0] + "/"
    segment_urls = [
        urljoin(base, line)
        for line in playlist.splitlines()
        if line and not line.startswith("#")
    ]

    # Download and concatenate segments
    with dest.open("wb") as fh:
        for seg_url in segment_urls:
            async with await self._get_with_retry(seg_url) as seg_resp:
                async for chunk in seg_resp.content.iter_chunked(1024):
                    fh.write(chunk)
```

---

## 5. MusicBrainz

### Source A: tagslut

**File**: `~/Projects/tagslut/src/tagslut/providers/musicbrainz.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `base_url` | `https://musicbrainz.org/ws/2` |
| `name` | `musicbrainz` |

#### Authentication

- **Type**: User-Agent header only
- **Required**: `user_agent` string (e.g., `"appname/version (contact@email.com)"`)

#### API Endpoints

| Endpoint | Method | inc Parameters |
|----------|--------|----------------|
| `/recording` | GET (search) | - |
| `/recording/{id}` | GET | `releases+artists` |
| `/release/{id}` | GET | `artists+recordings+release-groups` |

#### Key Methods

```python
async def search_track(self, query: str, *, limit: int = 5) -> List[Track]
async def get_track(self, external_id: str) -> Track
async def get_album(self, external_id: str) -> Album
```

#### Duration Field

```python
# MusicBrainz returns 'length' in MILLISECONDS (direct passthrough)
duration_ms = int(data.get("length", 0)) if data.get("length") else None
```

#### Cover Art Archive Integration

```python
if images.get("front") and data.get("id"):
    artwork = Artwork(
        url=f"https://coverartarchive.org/release/{data['id']}/front-500",
        mime_type="image/jpeg",
    )
```

---

### Source B: fla_cid Archive (With Rate Limiting)

**File**: `~/Projects/fla_cid/archive/exported-assets-12/musicbrainz_api.py`

#### Rate Limiting

```python
self.rate_limit_delay = 1.0  # MusicBrainz requires 1s between requests

# Enforced in finally block
finally:
    await asyncio.sleep(self.rate_limit_delay)
```

#### Metadata Normalization

```python
def normalize_metadata(self, recording_data: Dict[str, Any]) -> Dict[str, Any]:
    metadata = {
        "TITLE": recording.get("title"),
        "ARTIST": ", ".join(artists),
        "ALBUM": primary_release.get("title"),
        "DATE": primary_release.get("date"),
        "YEAR": primary_release.get("date", "")[:4],
        "MUSICBRAINZ_TRACKID": recording.get("id"),
        "MUSICBRAINZ_ALBUMID": primary_release.get("id"),
        "DURATION": str(int(recording.get("length", 0) / 1000)),  # ms to seconds
        "COUNTRY": primary_release.get("country"),
        "ISRC": isrcs[0] if isrcs else None,
        "GENRE": ", ".join(genre_names),
        "MUSICBRAINZ_ARTISTID": artist_credits[0].get("artist", {}).get("id"),
    }
```

---

## 6. Discogs

### Source A: flaccid

**File**: `~/Projects/flaccid/src/flaccid/plugins/discogs.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://api.discogs.com/` |

#### Authentication

- **Type**: Token header
- **Header**: `Authorization: Discogs token={token}`
- **Storage**: Keyring (`flaccid_discogs` / `token`)

#### Key Methods

```python
async def search_track(self, query: str) -> Any
async def get_track(self, track_id: str) -> TrackMetadata
async def get_album(self, album_id: str) -> AlbumMetadata
```

#### API Endpoints

| Endpoint | Method | Parameters |
|----------|--------|------------|
| `/database/search` | GET | `q`, `type=release` |
| `/tracks/{id}` | GET | - |
| `/releases/{id}` | GET | - |

---

### Source B: fla_cid Archive (With Rate Limiting)

**File**: `~/Projects/fla_cid/archive/exported-assets-12/discogs_api.py`

#### Rate Limiting

```python
self.rate_limit_delay = 1.0  # 1 second between requests

finally:
    await asyncio.sleep(self.rate_limit_delay)
```

#### Unique Metadata Fields

```python
metadata = {
    "ALBUM": release.get("title"),
    "ARTIST": ", ".join(release.get("artist", [])),
    "LABEL": ", ".join(release.get("label", [])),
    "YEAR": str(release.get("year", "")),
    "GENRE": ", ".join(release.get("genre", [])),
    "STYLE": ", ".join(release.get("style", [])),
    "COUNTRY": release.get("country"),
    "DISCOGS_RELEASE_ID": str(release.get("id", "")),
    "CATALOGNUMBER": release.get("catno"),
    "FORMAT": ", ".join(release.get("format", []))
}
```

---

## 7. Beatport

### Source: flaccid

**File**: `~/Projects/flaccid/src/flaccid/plugins/beatport.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://api.beatport.com/` |

#### Authentication

- **Type**: Bearer token
- **Header**: `Authorization: Bearer {token}`
- **Storage**: Keyring (`flaccid_beatport` / `token`)

#### Key Methods

```python
async def search_track(self, query: str) -> Any
async def get_track(self, track_id: str) -> TrackMetadata
async def get_album(self, album_id: str) -> AlbumMetadata
async def download_track(self, track_id: str, dest: Path) -> bool
```

#### Metadata Mapping

```python
TrackMetadata(
    title=data.get("name", ""),
    artist=data.get("artists", [{}])[0].get("name", ""),
    album=data.get("release", {}).get("name", ""),
    track_number=int(data.get("number", 0)),
    disc_number=1,
    source="beatport",
)
```

---

## 8. Lyrics Providers

### Lyrics.ovh (Free, No Auth)

**File**: `~/Projects/flaccid/src/flaccid/plugins/lyrics.py`

```python
class LyricsOvhProvider(LyricsProviderPlugin):
    BASE_URL = "https://api.lyrics.ovh/v1/"

    async def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        url = f"{self.BASE_URL}{artist}/{title}"
        async with self.session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
        return data.get("lyrics", "").strip() or None
```

### Genius

**File**: `~/Projects/flaccid/src/flaccid/plugins/genius.py`

#### Configuration

| Parameter | Description |
|-----------|-------------|
| `BASE_URL` | `https://api.genius.com` |
| `token` | Environment variable: `GENIUS_TOKEN` |

#### Authentication

- **Type**: Bearer token
- **Header**: `Authorization: Bearer {token}`

#### Lookup Flow

1. Search for song: `GET /search?q={artist} {title}`
2. Extract song ID from first hit
3. Get song details: `GET /songs/{song_id}`
4. Extract lyrics from response

### Combined Lyrics Plugin with Caching

```python
class LyricsPlugin(LyricsProviderPlugin):
    def __init__(self, cache_size: int = 128):
        self.providers = [
            LyricsOvhProvider(),
            GeniusPlugin(),      # If available
            MusixmatchPlugin(),  # If available
        ]
        self.cache = _LRUCache(cache_size)

    async def get_lyrics(self, artist: str, title: str) -> Optional[str]:
        key = f"{artist.lower()}::{title.lower()}"

        # Check memory cache
        if cached := self.cache.get(key):
            return cached

        # Check disk cache
        if disk_cached := metadata.get_cached_lyrics(key):
            self.cache.set(key, disk_cached)
            return disk_cached

        # Try each provider
        for provider in self.providers:
            try:
                lyrics = await provider.get_lyrics(artist, title)
                if lyrics:
                    self.cache.set(key, lyrics)
                    metadata.set_cached_lyrics(key, lyrics)
                    return lyrics
            except Exception:
                continue

        return None
```

---

## 9. Base Classes & Data Models

### tagslut Data Models

**File**: `~/Projects/tagslut/src/tagslut/core/models.py`

```python
class Track(BaseModel):
    title: str
    artists: List[Artist]
    album: Optional[Album] = None
    duration_ms: Optional[int] = None  # Milliseconds
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    explicit: bool = False
    providers: List[ProviderInfo] = []
    isrc: Optional[str] = None
    upc: Optional[str] = None

class Album(BaseModel):
    title: str
    artists: List[Artist]
    release_date: Optional[datetime] = None
    artwork: Optional[Artwork] = None
    providers: List[ProviderInfo] = []

class Artwork(BaseModel):
    url: HttpUrl
    mime_type: str = "image/jpeg"
    width: Optional[int] = None
    height: Optional[int] = None
```

### flaccid Data Models

**File**: `~/Projects/flaccid/src/flaccid/plugins/base.py`

```python
@dataclass
class TrackMetadata:
    title: str
    artist: str
    album: str
    track_number: int
    disc_number: int
    year: Optional[int] = None
    isrc: Optional[str] = None
    art_url: Optional[str] = None
    lyrics: Optional[str] = None
    source: Optional[str] = None  # Provider name for provenance

@dataclass
class AlbumMetadata:
    title: str
    artist: str
    year: Optional[int] = None
    cover_url: Optional[str] = None
```

### Abstract Base Classes

```python
class MusicProvider(abc.ABC):
    """tagslut base class"""

    @abc.abstractmethod
    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]: ...

    @abc.abstractmethod
    async def get_track(self, external_id: str) -> Track: ...

    @abc.abstractmethod
    async def get_album(self, external_id: str) -> Album: ...

class MetadataProviderPlugin(MusicServicePlugin, ABC):
    """flaccid base class"""

    @abstractmethod
    async def authenticate(self) -> None: ...

    @abstractmethod
    async def search_track(self, query: str) -> Any: ...

    @abstractmethod
    async def get_track(self, track_id: str) -> TrackMetadata: ...

    @abstractmethod
    async def get_album(self, album_id: str) -> AlbumMetadata: ...
```

---

## 10. Cascade & Fallback Patterns

### Metadata Merge Strategies

**File**: `~/Projects/flaccid/src/flaccid/core/metadata/cascade.py`

| Strategy | Behavior |
|----------|----------|
| `prefer` | Use first non-empty value (default) |
| `replace` | Always use latest value |
| `append` | Concatenate string values |

### Cascade Function

```python
def cascade(
    *sources: TrackMetadata,
    strategies: dict[str, str] | None = None,
) -> TrackMetadata:
    """Merge metadata objects using optional per-field strategies."""

    merged = TrackMetadata(**asdict(sources[0]))
    strategies = strategies or {}

    for src in sources[1:]:
        for field in fields(TrackMetadata):
            val = getattr(merged, field.name)
            other = getattr(src, field.name)

            if other in (None, ""):
                continue

            strategy = strategies.get(field.name, "prefer")

            if strategy == "replace":
                setattr(merged, field.name, other)
            elif strategy == "append":
                if val in (None, ""):
                    setattr(merged, field.name, other)
                elif isinstance(val, str) and isinstance(other, str):
                    setattr(merged, field.name, val + other)
            else:  # prefer
                if val in (None, ""):
                    setattr(merged, field.name, other)

    return merged
```

### Provenance Tracking

```python
def cascade_with_provenance(
    *sources: TrackMetadata,
    strategies: dict[str, str] | None = None,
) -> tuple[TrackMetadata, dict[str, str]]:
    """Merge and record which provider contributed each field."""

    merged = cascade(*sources, strategies=strategies)
    provenance: dict[str, str] = {}

    for field in fields(TrackMetadata):
        for src in reversed(sources):
            val = getattr(src, field.name)
            if val not in (None, ""):
                provenance[field.name] = src.source or "unknown"
                break

    return merged, provenance

# Example output:
# provenance = {
#     "title": "qobuz",
#     "artist": "tidal",
#     "album": "qobuz+tidal",  # append strategy
#     "year": "apple"
# }
```

### Precedence-Based Merge

```python
def merge_by_precedence(
    results: dict[str, TrackMetadata],
    *,
    strategies: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> TrackMetadata:
    """Merge respecting configured plugin precedence."""

    order = get_precedence_order(list(results.keys()), settings=settings)
    ordered = [results[name] for name in order]
    return cascade(*ordered, strategies=strategies)
```

---

## 11. Error Handling

### Exception Hierarchy (flaccid)

```python
class FLACCIDError(Exception):
    """Base exception for all FLACCID errors."""

class PluginError(FLACCIDError):
    """Base class for plugin-related failures."""

class AuthenticationError(PluginError):
    """Raised when authentication with an external service fails."""

class APIError(PluginError):
    """Raised when an API request returns an error response."""

class DownloadError(PluginError):
    """Raised when a download from an external service fails."""
```

### Error Handling Patterns

#### HTTP Status Check (tagslut)

```python
async def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
    response = await self._client.request(method, url, **kwargs)
    if response.status_code >= 400:
        raise ProviderError(
            f"{self.name} responded with status {response.status_code}: {response.text}"
        )
    return response.json()
```

#### Credential Validation

```python
async def authenticate(self) -> None:
    if not self.app_id:
        raise AuthenticationError("Qobuz App ID is not configured")

    username = keyring.get_password("flaccid_qobuz", "username")
    password = keyring.get_password("flaccid_qobuz", "password")

    if not username or not password:
        raise AuthenticationError("Credentials missing. Run 'fla set auth' first.")
```

#### Graceful Degradation

```python
# Lyrics plugin: continue on failure
for provider in self.providers:
    try:
        lyrics = await provider.get_lyrics(artist, title)
        if lyrics:
            return lyrics
    except Exception as exc:
        logger.warning("Provider %s failed: %s", provider.__class__.__name__, exc)
        continue

return None
```

---

## 12. File Download Utilities

**File**: `~/Projects/flaccid/src/flaccid/core/downloader.py`

### Features

- 8KB chunked downloads
- Temporary file with atomic rename
- Content-Length header parsing
- Progress bar integration (Rich)
- Error cleanup

### Implementation

```python
async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: Path,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
) -> bool:
    temp_path = dest_path.with_suffix(".tmp")
    os.makedirs(dest_path.parent, exist_ok=True)

    try:
        async with session.get(url) as response:
            if not response.ok:
                return False

            total_size = int(response.headers.get("Content-Length", 0))
            if progress and task_id is not None:
                progress.update(task_id, total=total_size)

            with open(temp_path, "wb") as f:
                bytes_downloaded = 0
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, completed=bytes_downloaded)

        # Atomic rename
        temp_path.rename(dest_path)
        return True

    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        return False
```

---

## 13. Configuration Management

### tagslut Configuration

**File**: `~/Projects/tagslut/src/tagslut/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TAGSLUT_")

    # Spotify
    spotify_client_id: Optional[str] = None
    spotify_client_secret: Optional[str] = None
    spotify_access_token: Optional[str] = None

    # Qobuz
    qobuz_app_id: Optional[str] = None
    qobuz_app_secret: Optional[str] = None

    # Tidal
    tidal_token: Optional[str] = None
    tidal_session_id: Optional[str] = None

    # Apple Music
    apple_music_key: Optional[str] = None
    apple_music_team_id: Optional[str] = None
    apple_music_key_id: Optional[str] = None

    # MusicBrainz
    musicbrainz_app_name: str = "tagslut"
    musicbrainz_app_version: str = "0.1.0"
    musicbrainz_contact: Optional[str] = None
```

### flaccid Configuration

**File**: `~/Projects/flaccid/src/flaccid/core/config.py`

#### Configuration Sources (Priority Order)

1. Project-local `.secrets.toml`
2. User-scoped `~/.config/flaccid/settings.toml`
3. Environment variables

```python
class Settings(BaseModel):
    qobuz_app_id: str = ""
    download_path: str = ""
    library_path: str = ""
    cache_path: str = ""
    plugin_precedence: list[str] = []  # e.g., ["qobuz", "tidal", "apple"]

def load_settings() -> Settings:
    raw_loader = Dynaconf(
        settings_files=[".secrets.toml", str(user_settings_file)],
        environments=True,
        env="default",
    )
    # ... validate and return Settings
```

### Keyring Storage Keys

| Service | Keyring Service | Keys |
|---------|-----------------|------|
| Qobuz | `flaccid_qobuz` | `username`, `password` |
| Tidal | `flaccid_tidal` | `username`, `password`, `refresh_token` |
| Beatport | `flaccid_beatport` | `token` |
| Discogs | `flaccid_discogs` | `token` |

---

## 14. Duration/Length Retrieval

| Provider | Source Field | Input Unit | Conversion |
|----------|--------------|------------|------------|
| **Spotify** | `duration_ms` | milliseconds | None (direct) |
| **Apple Music** | `durationInMillis` | milliseconds | None (direct) |
| **Qobuz** | `duration` | seconds | `× 1000` |
| **Tidal** | `duration` | seconds | `× 1000` |
| **MusicBrainz** | `length` | milliseconds | None (direct) |
| **Discogs** | N/A | - | Not provided |
| **Beatport** | N/A | - | Not provided |

### Conversion Examples

```python
# Qobuz / Tidal (seconds to milliseconds)
duration_ms = int(data.get("duration", 0)) * 1000 if data.get("duration") else None

# Spotify / Apple / MusicBrainz (direct passthrough)
duration_ms = data.get("duration_ms")  # or durationInMillis, length
```

---

## 15. Dependencies

### Core Runtime

```
# HTTP Clients
httpx>=0.27.0              # tagslut (sync httpx.AsyncClient)
aiohttp>=3.8.0             # flaccid, fla_cid (async)

# Data Validation
pydantic>=2.6.0            # Data models and settings
pydantic-settings>=2.2.1   # Environment variable loading

# Configuration
dynaconf>=3.1.0            # Hierarchical config (flaccid)
python-dotenv>=1.0.0       # .env file support
tomlkit>=0.13.0            # TOML file manipulation

# Credential Storage
keyring>=24.0.0            # Secure credential storage

# CLI/UI
typer>=0.12.0              # CLI framework
rich>=13.0.0               # Terminal UI and progress bars

# Audio Metadata
mutagen>=1.47.0            # FLAC/MP3 tag manipulation
```

### Install Command

```bash
pip install httpx aiohttp pydantic pydantic-settings dynaconf python-dotenv keyring typer rich mutagen
```

---

## 16. API Endpoints Quick Reference

| Service | Base URL | Auth Type | Rate Limit |
|---------|----------|-----------|------------|
| **Spotify** | `https://api.spotify.com/v1` | Bearer token | API-managed |
| **Apple Music** | `https://api.music.apple.com/v1` | JWT Bearer | API-managed |
| **iTunes** | `https://itunes.apple.com/search` | None | API-managed |
| **Qobuz** | `https://www.qobuz.com/api.json/0.2` | app_id + signed | API-managed |
| **Tidal** | `https://api.tidalhifi.com/v1` | Bearer | Retry-After |
| **Tidal Auth** | `https://auth.tidal.com/v1/oauth2/token` | - | - |
| **MusicBrainz** | `https://musicbrainz.org/ws/2` | User-Agent | 1 req/sec |
| **Discogs** | `https://api.discogs.com` | `Discogs token=` | 1 req/sec |
| **Beatport** | `https://api.beatport.com/` | Bearer token | Unknown |
| **Genius** | `https://api.genius.com` | Bearer token | API-managed |
| **Lyrics.ovh** | `https://api.lyrics.ovh/v1/` | None | Unknown |

---

## Appendix: File Locations

### tagslut

| Component | Path |
|-----------|------|
| Providers | `~/Projects/tagslut/src/tagslut/providers/` |
| Models | `~/Projects/tagslut/src/tagslut/core/models.py` |
| Config | `~/Projects/tagslut/src/tagslut/core/config.py` |
| Base Class | `~/Projects/tagslut/src/tagslut/providers/base.py` |

### flaccid

| Component | Path |
|-----------|------|
| Plugins | `~/Projects/flaccid/src/flaccid/plugins/` |
| Base Class | `~/Projects/flaccid/src/flaccid/plugins/base.py` |
| Config | `~/Projects/flaccid/src/flaccid/core/config.py` |
| Errors | `~/Projects/flaccid/src/flaccid/core/errors.py` |
| Downloader | `~/Projects/flaccid/src/flaccid/core/downloader.py` |
| Cascade | `~/Projects/flaccid/src/flaccid/core/metadata/cascade.py` |

### fla_cid Archive

| Component | Path |
|-----------|------|
| Discogs | `~/Projects/fla_cid/archive/exported-assets-12/discogs_api.py` |
| MusicBrainz | `~/Projects/fla_cid/archive/exported-assets-12/musicbrainz_api.py` |

---

*End of Report*
