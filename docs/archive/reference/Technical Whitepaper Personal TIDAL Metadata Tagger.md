# Technical Whitepaper: Personal TIDAL Metadata Tagger

## Architectural Design Document

**Version**: 1.0 | **Date**: 2026-03-29 | **Classification**: Technical Reference

---

## Executive Summary

This whitepaper provides a production-ready roadmap for building a Personal TIDAL Metadata Tagger—a tool that extracts high-quality metadata from TIDAL’s streaming service using an active personal subscription. Unlike Qobuz’s reverse-engineering approach, TIDAL offers an official OAuth2-based developer API, making credential acquisition legitimate and straightforward.

The architecture leverages TIDAL’s official API endpoints accessed via OAuth2 authorization flows, implements session management with refresh token rotation, and embeds metadata into local audio files (FLAC/MP3) according to industry standards.

**Key Distinction from Qobuz**: TIDAL provides an official developer portal for application registration. No credential scraping or reverse engineering of JavaScript bundles is required. This significantly reduces legal exposure and maintenance burden.

---

## 1. Credential Acquisition & Session Management

### 1.1 Official Application Registration

Unlike Qobuz, TIDAL offers an official developer program. To obtain API credentials:

1. **Register an application** at TIDAL’s developer website
2. **Obtain credentials**: After registration, you receive:
   - `CLIENT_ID` (public identifier)
   - `CLIENT_SECRET` (confidential credential for server-side apps)

**Redirect URI Requirement**: When creating the TIDAL app, you must specify a `REDIRECT_URI` (e.g., `http://localhost:8080/callback`) that must exactly match the URI used in authorization requests .

### 1.2 OAuth2 Authentication Flow

TIDAL implements the **OAuth2 Authorization Code Flow with PKCE** (Proof Key for Code Exchange), defined in RFC 7636. This flow is more secure than basic OAuth2 and works for both server-side and native applications .

#### 1.2.1 PKCE Flow Implementation (Python)

```python
import requests
import secrets
import hashlib
import base64
from typing import Dict, Optional

class TidalAuthenticator:
    """Handles TIDAL OAuth2 PKCE authentication flow."""
    
    AUTHORIZE_URL = "https://login.tidal.com/oauth2/authorize"
    TOKEN_URL = "https://login.tidal.com/oauth2/token"
    
    def __init__(self, client_id: str, redirect_uri: str):
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.session = requests.Session()
    
    def generate_pkce_pair(self) -> tuple[str, str]:
        """
        Generate PKCE code_verifier and code_challenge.
        
        The code_verifier is a cryptographically random string.
        The code_challenge is the SHA256 hash (base64url encoded) of the verifier.
        """
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')
        return code_verifier, code_challenge
    
    def get_authorization_url(self, scope: list[str]) -> str:
        """Generate the authorization URL for user consent."""
        verifier, challenge = self.generate_pkce_pair()
        state = secrets.token_urlsafe(16)
        
        # Store verifier and state for callback verification
        self._pending_verifier = verifier
        self._pending_state = state
        
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scope),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state
        }
        
        # Construct URL
        return f"{self.AUTHORIZE_URL}?{requests.compat.urlencode(params)}"
    
    def exchange_code_for_tokens(self, code: str, state: str) -> Dict:
        """
        Exchange authorization code for access and refresh tokens.
        
        Requires the original code_verifier from PKCE generation.
        """
        if state != self._pending_state:
            raise ValueError("State mismatch - possible CSRF attack")
        
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self._pending_verifier
        }
        
        response = requests.post(self.TOKEN_URL, data=payload)
        response.raise_for_status()
        
        token_data = response.json()
        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_in": token_data["expires_in"],
            "token_type": token_data.get("token_type", "Bearer")
        }
    
    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh an expired access token using the refresh token.
        
        Implements refresh token rotation - the old refresh token may be invalidated
        and a new one returned .
        """
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret  # Required for refresh
        }
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "TIDAL-Metadata-Tagger/1.0"
        }
        
        response = requests.post(self.TOKEN_URL, data=payload, headers=headers)
        
        if response.status_code == 200:
            token_data = response.json()
            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "expires_in": token_data["expires_in"]
            }
        else:
            raise Exception(f"Token refresh failed: {response.status_code}, {response.text}")
```

#### 1.2.2 OAuth2 Roles and Responsibilities

TIDAL’s OAuth2 implementation follows the standard four-role model defined in RFC 6749 :

| Role                     | TIDAL Implementation        | Responsibility                                               |
| ------------------------ | --------------------------- | ------------------------------------------------------------ |
| **Resource Owner**       | TIDAL User                  | Controls access to personal data (playlists, favorites, account info) |
| **Client**               | Metadata Tagger Application | Requests authorization, manages tokens, calls APIs           |
| **Authorization Server** | `login.tidal.com/oauth2`    | Authenticates users, issues tokens, validates credentials    |
| **Resource Server**      | `api.tidal.com/v1`          | Hosts music metadata, artwork, streaming URLs                |

**Authorization Server vs Resource Server Separation** : 
- Authorization endpoints: `login.tidal.com/oauth2/authorize` and `/oauth2/token`
- Resource endpoints: `api.tidal.com/v1/` (metadata), CDN endpoints (audio streams)

### 1.3 Token Management Strategy

TIDAL access tokens have a limited lifetime (typically 3600 seconds). Implement persistent token storage and automatic refresh:

```python
import json
from pathlib import Path
from datetime import datetime, timedelta

class TokenManager:
    """Persistent token storage with auto-refresh capability."""
    
    def __init__(self, storage_path: Path, authenticator: TidalAuthenticator):
        self.storage_path = storage_path
        self.auth = authenticator
        self._load_tokens()
    
    def _load_tokens(self):
        """Load tokens from disk, or initialize empty."""
        if self.storage_path.exists():
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                self.access_token = data.get('access_token')
                self.refresh_token = data.get('refresh_token')
                self.expires_at = datetime.fromisoformat(data.get('expires_at', '1970-01-01'))
        else:
            self.access_token = None
            self.refresh_token = None
            self.expires_at = datetime.min
    
    def _save_tokens(self):
        """Persist tokens to disk."""
        with open(self.storage_path, 'w') as f:
            json.dump({
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.expires_at.isoformat()
            }, f)
    
    def get_valid_access_token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if self.access_token and datetime.now() < self.expires_at - timedelta(minutes=5):
            return self.access_token
        
        # Token expired or expiring soon - refresh
        if self.refresh_token:
            new_tokens = self.auth.refresh_access_token(self.refresh_token)
            self.access_token = new_tokens['access_token']
            self.refresh_token = new_tokens.get('refresh_token', self.refresh_token)
            self.expires_at = datetime.now() + timedelta(seconds=new_tokens['expires_in'])
            self._save_tokens()
            return self.access_token
        
        raise ValueError("No valid tokens available. Re-authentication required.")
```

### 1.4 Legal Considerations

Since TIDAL provides an official developer API, legal exposure is minimal compared to the Qobuz approach. Key compliance points:

- **Terms of Service**: Review TIDAL’s Developer Terms—most restrict redistribution of content but permit personal metadata access
- **Rate Limiting**: Official APIs typically have documented rate limits; exceeding them may result in temporary or permanent suspension
- **Commercial Use**: Personal metadata tagging is generally permissible; redistributing TIDAL metadata or audio is not

**Recommendation**: Register as a developer and use official credentials. This provides a stable, documented interface without the maintenance burden of reverse engineering.

---

## 2. API Architecture & Endpoint Mapping

### 2.1 Base URL and Authentication

TIDAL’s API uses the base URL `https://api.tidal.com/v1/`. All requests require an access token in the Authorization header:

```http
GET /v1/albums/{album_id}
Authorization: Bearer {access_token}
```

### 2.2 Core Metadata Endpoints

The following endpoints are derived from TIDAL’s official API documentation (available to registered developers):

#### 2.2.1 Album Metadata

```http
GET /v1/albums/{album_id}
```

**Response Structure** (typical fields):

| Field             | Type    | Description                    |
| ----------------- | ------- | ------------------------------ |
| `id`              | integer | Unique album identifier        |
| `title`           | string  | Album title                    |
| `upc`             | string  | Universal Product Code         |
| `numberOfTracks`  | integer | Total track count              |
| `numberOfVolumes` | integer | Disc count (multi-disc albums) |
| `releaseDate`     | string  | Release date (YYYY-MM-DD)      |
| `copyright`       | string  | Copyright notice               |
| `explicit`        | boolean | Explicit content flag          |
| `audioQuality`    | string  | "LOSSLESS", "HI_RES", etc.     |
| `artist`          | object  | Primary artist information     |
| `artists`         | array   | All contributing artists       |

#### 2.2.2 Track Metadata

```http
GET /v1/tracks/{track_id}
```

**Response Structure**:

| Field          | Type    | Description                                |
| -------------- | ------- | ------------------------------------------ |
| `id`           | integer | Unique track identifier                    |
| `title`        | string  | Track title                                |
| `version`      | string  | Version (e.g., "Remastered", "Radio Edit") |
| `trackNumber`  | integer | Position on album                          |
| `volumeNumber` | integer | Disc number                                |
| `isrc`         | string  | International Standard Recording Code      |
| `duration`     | integer | Duration in milliseconds                   |
| `explicit`     | boolean | Explicit lyrics flag                       |
| `audioQuality` | string  | Maximum available quality                  |
| `streamReady`  | boolean | Full stream availability                   |

#### 2.2.3 Artist Metadata

```http
GET /v1/artists/{artist_id}
```

#### 2.2.4 Search Endpoint

```http
GET /v1/search?query={query}&types=TRACKS,ALBUMS,ARTISTS
```

### 2.3 PHP Implementation Reference

A PHP wrapper for TIDAL’s API is available via Packagist (`gerenuk/php-tidal-api`) . Usage example:

```php
require 'vendor/autoload.php';

$api = new TidalApi\TidalApi();
$api->setAccessToken($accessToken);

// Retrieve authenticated user's playlists
$playlists = $api->getMyPlaylists();
```

### 2.4 Classical Music Metadata Handling

**Documentation Gap**: TIDAL’s approach to classical music metadata (movements vs works) is not publicly documented. Based on observed API responses, the following patterns are expected:

```
Standard Track (Pop):
- title: "Bohemian Rhapsody"
- version: null

Classical Track (TIDAL):
- title: "Piano Sonata No. 14 in C-sharp minor, Op. 27 No. 2"
- version: "Adagio sostenuto" (movement indicator)
```

**Implementation Strategy**:

```python
def extract_classical_metadata(track: dict) -> dict:
    """Handle TIDAL classical music metadata patterns."""
    metadata = {}
    
    # Version field often contains movement information
    if track.get("version"):
        metadata["movement"] = track["version"]
        
        # If title contains work name and version is movement,
        # combine for full display
        if track.get("title") and track.get("version"):
            metadata["combined_title"] = f"{track['title']}: {track['version']}"
    
    # Artist role distinction (composer vs performer) may require
    # examining artist contributions array
    
    return metadata
```

---

## 3. Comparative Analysis of Existing Tools

### 3.1 Official API Clients

**PHP TIDAL API Wrapper** :
- **Repository**: `gerenuk/php-tidal-api`
- **License**: MIT
- **Features**: OAuth2 PKCE support, scope-based authorization, playlist management
- **Limitations**: PHP-only, minimal metadata extraction for tagging

### 3.2 Community Reverse-Engineering Projects

The following open-source projects have performed unofficial TIDAL API analysis. Their architectures provide valuable patterns for metadata extraction:

| Project                             | Key Insight                             | Relevance to Metadata Tagger      |
| ----------------------------------- | --------------------------------------- | --------------------------------- |
| **tidal-dl** (Python)               | Token extraction from TIDAL desktop app | Session persistence patterns      |
| **Tidal-Media-Downloader** (Python) | Metadata parsing from API responses     | JSON-to-tag mapping strategies    |
| **tidalapi** (Go)                   | OAuth2 device flow implementation       | Alternative authentication method |

**Note**: Unlike Qobuz, TIDAL’s official API eliminates the need for credential scraping. These community projects primarily exist to download audio, not for metadata extraction alone.

---

## 4. Metadata Embedding Standards

### 4.1 Field Mapping Table: TIDAL API → Audio Tags

| TIDAL API Field | FLAC (Vorbis Comment) | MP3 (ID3v2.4)     | Notes                      |
| --------------- | --------------------- | ----------------- | -------------------------- |
| `title`         | `TITLE`               | `TIT2`            | Primary track title        |
| `version`       | `VERSION`             | `TIT3` (Subtitle) | Movement/edition info      |
| `trackNumber`   | `TRACKNUMBER`         | `TRCK`            | Format: `{number}/{total}` |
| `volumeNumber`  | `DISCNUMBER`          | `TPOS`            | Multi-disc albums          |
| `isrc`          | `ISRC`                | `TSRC`            | Recording identifier       |
| `upc`           | `UPC`                 | Not standard      | Use TXXX frame             |
| `artist.name`   | `ARTIST`              | `TPE1`            | Track artist               |
| `albumArtist`   | `ALBUMARTIST`         | `TPE2`            | Album-level artist         |
| `album.title`   | `ALBUM`               | `TALB`            | Album title                |
| `copyright`     | `COPYRIGHT`           | `TCOP`            | Copyright notice           |
| `releaseDate`   | `DATE`                | `TDRC`            | Format: YYYY-MM-DD         |
| `duration`      | `LENGTH`              | `TLEN`            | Milliseconds               |
| `explicit`      | `EXPLICIT`            | `TXXX:EXPLICIT`   | Flag for explicit content  |
| `audioQuality`  | `SOURCE_QUALITY`      | `TXXX:QUALITY`    | "LOSSLESS", "HI_RES"       |

### 4.2 Artwork Handling

TIDAL provides artwork URLs with multiple size variants. The highest quality artwork is typically available at:

```python
def get_highest_quality_artwork(album_data: dict) -> str:
    """
    Extract the highest quality artwork URL from album metadata.
    
    TIDAL typically provides images at:
    - 160x160 (thumbnail)
    - 320x320 (medium)
    - 640x640 (large)
    - 1280x1280 (original)
    """
    # Check for image array in response
    if "images" in album_data and album_data["images"]:
        # Last image is typically largest
        return album_data["images"][-1]["url"]
    
    # Alternative: construct from base pattern
    album_id = album_data.get("id")
    return f"https://resources.tidal.com/images/{album_id}/1280x1280.jpg"
```

---

## 5. Operational Safety & Fallbacks

### 5.1 Rate Limiting

TIDAL’s official API has documented rate limits. Based on community analysis and developer documentation:

| Operation     | Recommended Delay | Notes                |
| ------------- | ----------------- | -------------------- |
| Album lookup  | 0.3 seconds       | Lightweight metadata |
| Track lookup  | 0.2 seconds       | Very fast            |
| Search        | 1.0 second        | Resource-intensive   |
| Token refresh | As needed         | Only when expired    |

### 5.2 Fallback Logic

While TIDAL’s metadata is generally comprehensive, fallbacks may be needed for:

- **BPM (Tempo)**: Not provided by TIDAL API
- **Detailed classical work structure**: Limited in standard responses
- **Composer vs performer distinction**: May require parsing artist credits

**Fallback Strategy**:

```python
class TidalMetadataEnricher:
    """Enrich TIDAL metadata with data from alternative sources."""
    
    async def enrich_track(self, tidal_track: dict) -> dict:
        enriched = tidal_track.copy()
        
        # MusicBrainz enrichment (via ISRC)
        if "isrc" in tidal_track:
            mb_result = await self.musicbrainz.lookup_by_isrc(
                tidal_track["isrc"]
            )
            if mb_result:
                if "bpm" not in enriched and mb_result.get("bpm"):
                    enriched["bpm"] = mb_result["bpm"]
                if "composer" not in enriched and mb_result.get("composer"):
                    enriched["composer"] = mb_result["composer"]
        
        return enriched
```

### 5.3 Error Recovery

```python
class ResilientTidalClient:
    """Handles API errors with appropriate recovery strategies."""
    
    async def request_with_retry(self, endpoint: str, params: dict = None):
        for attempt in range(3):
            try:
                token = self.token_manager.get_valid_access_token()
                response = await self.session.get(
                    endpoint,
                    params=params,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                if response.status_code == 401:
                    # Token expired - force refresh and retry
                    await self.token_manager.force_refresh()
                    continue
                
                if response.status_code == 429:
                    # Rate limited - exponential backoff
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except aiohttp.ClientError as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(1)
```

---

## Appendix: Complete OAuth2 Device Flow Alternative

For headless environments (servers, CLI tools without browsers), TIDAL supports OAuth2 Device Authorization Grant (RFC 8628):

```python
def device_authorization_flow(client_id: str) -> Dict:
    """
    OAuth2 Device Flow for headless authentication.
    
    User visits a URL on any device and enters a code.
    """
    # Step 1: Request device code
    device_response = requests.post(
        "https://login.tidal.com/oauth2/device_authorization",
        data={"client_id": client_id, "scope": "playlists.read offline_access"}
    )
    device_data = device_response.json()
    
    # Display to user
    print(f"Visit: {device_data['verification_uri_complete']}")
    print(f"Or enter code: {device_data['user_code']}")
    
    # Step 2: Poll for token
    interval = device_data['interval']
    while True:
        time.sleep(interval)
        token_response = requests.post(
            "https://login.tidal.com/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_data['device_code'],
                "client_id": client_id
            }
        )
        
        if token_response.status_code == 200:
            return token_response.json()
        elif token_response.status_code == 400:
            error = token_response.json().get("error")
            if error == "authorization_pending":
                continue
            elif error == "expired_token":
                raise Exception("Device code expired")
```

---

## References

1. gerenuk, "PHP TIDAL API Wrapper," Packagist, 2026. 

2. "TIDAL API Reverse Engineering: OAuth2 and RESTful Interface Analysis," CSDN Blog, 2025. 

3. TIDAL Developer Portal (Official) — Available to registered developers