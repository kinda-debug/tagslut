"""
Apple Music API provider.

Uses the authenticated Apple Music API (amp-api.music.apple.com) which provides
richer metadata than the public iTunes Search API, including:
- ISRC, UPC, copyright
- Credits (composer, performers)
- Lyrics (TTML format)
- Classical metadata (work, movement)
- High-resolution artwork

Authentication is handled by extracting a bearer token from the Apple Music web app,
similar to the approach used by MP3Tag's Apple Music Web Source.
"""

import logging
import re
import time
from typing import Optional, List, Dict, Any

from tagslut.metadata.models.types import ProviderTrack, MatchConfidence
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.apple_music")


class AppleMusicProvider(AbstractProvider):
    """
    Apple Music API provider using dynamic bearer token extraction.

    Token is extracted from the Apple Music web app's JavaScript bundle,
    which contains an embedded JWT for API access.

    Supports:
    - Text search: GET /v1/catalog/{country}/search?types=songs&term={query}
    - Track by ID: GET /v1/catalog/{country}/songs/{id}?include=credits,lyrics
    - ISRC search: Client-side filtering on search results
    """

    name = "apple_music"
    supports_isrc_search = False  # Filter client-side

    rate_limit_config = RateLimitConfig(
        min_delay=0.5,
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://amp-api.music.apple.com"
    TOKEN_SOURCE_URL = "https://beta.music.apple.com/"
    COUNTRY = "us"

    # Token caching
    TOKEN_CACHE_DURATION = 3600  # 1 hour

    def __init__(self, token_manager=None):  # type: ignore  # TODO: mypy-strict
        super().__init__(token_manager)
        self._cached_token: Optional[str] = None
        self._token_fetched_at: float = 0

    def _extract_bearer_token(self) -> Optional[str]:
        """
        Extract bearer token from Apple Music web app.

        Flow:
        1. Fetch https://beta.music.apple.com/
        2. Find JS bundle URL matching /(assets/index-legacy-[^/]+\\.js)/
        3. Fetch that JS file
        4. Extract token using pattern (?=eyJh)(.*?)(?=")

        Returns:
            Bearer token string (without "Bearer " prefix), or None if extraction fails
        """
        try:
            # Step 1: Fetch main page
            response = self.client.get(
                self.TOKEN_SOURCE_URL,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=30.0,
            )
            if response.status_code != 200:
                logger.warning("Failed to fetch Apple Music web app: %d", response.status_code)
                return None

            # Step 2: Find JS bundle URL
            match = re.search(r"/(assets/index-legacy-[^/]+\.js)", response.text)
            if not match:
                # Try alternative patterns
                match = re.search(r"/(assets/index[^\"']+\.js)", response.text)
            if not match:
                logger.warning("Could not find Apple Music JS bundle URL")
                return None

            js_path = match.group(1)
            js_url = f"{self.TOKEN_SOURCE_URL}{js_path}"

            # Step 3: Fetch JS bundle
            js_response = self.client.get(
                js_url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
                timeout=30.0,
            )
            if js_response.status_code != 200:
                logger.warning("Failed to fetch Apple Music JS bundle: %d", js_response.status_code)
                return None

            # Step 4: Extract token (starts with eyJh - base64 encoded JWT header)
            token_match = re.search(r'(?=eyJh)(.*?)(?=")', js_response.text)
            if not token_match:
                logger.warning("Could not extract bearer token from JS bundle")
                return None

            token = token_match.group(1)
            logger.debug("Successfully extracted Apple Music bearer token")
            return token

        except Exception as e:
            logger.error("Error extracting Apple Music bearer token: %s", e)
            return None

    def _get_bearer_token(self) -> Optional[str]:
        """Get valid bearer token, refreshing if needed."""
        now = time.time()
        if self._cached_token and (now - self._token_fetched_at) < self.TOKEN_CACHE_DURATION:
            return self._cached_token

        # Fetch fresh token
        token = self._extract_bearer_token()
        if token:
            self._cached_token = token
            self._token_fetched_at = now
        return token

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with bearer token."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://music.apple.com",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        }
        token = self._get_bearer_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Apple Music ID.

        Args:
            track_id: Apple Music track/song ID

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        url = f"{self.BASE_URL}/v1/catalog/{self.COUNTRY}/songs/{track_id}"
        params = {"include": "credits,lyrics,albums"}

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch Apple Music track %s", track_id)
            return None

        try:
            data = response.json()
            tracks = data.get("data", [])
            if not tracks:
                return None

            track = self._normalize_track(tracks[0])
            track.match_confidence = MatchConfidence.EXACT
            return track
        except Exception as e:
            logger.error("Failed to parse Apple Music track response: %s", e)
            return None

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Args:
            query: Search query (e.g., "artist title")
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        url = f"{self.BASE_URL}/v1/catalog/{self.COUNTRY}/search"
        params = {
            "types": "songs",
            "term": query,
            "limit": min(limit, 25),
            "include[songs]": "credits,lyrics",
        }

        response = self._make_request("GET", url, params=params)
        if response is None or response.status_code != 200:
            logger.warning("Apple Music search failed for query: %s", query)
            return []

        try:
            data = response.json()
            songs_data = data.get("results", {}).get("songs", {}).get("data", [])
            return [self._normalize_track(t) for t in songs_data]
        except Exception as e:
            logger.error("Failed to parse Apple Music search response: %s", e)
            return []

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Search for tracks by ISRC.

        Uses text search with ISRC, then filters results client-side.

        Args:
            isrc: International Standard Recording Code

        Returns:
            List of ProviderTrack with matching ISRC
        """
        results = self.search(isrc, limit=25)
        return [t for t in results if t.isrc and t.isrc.upper() == isrc.upper()]

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Apple Music track object to ProviderTrack.

        Apple Music track structure:
        {
            "id": "...",
            "type": "songs",
            "attributes": {
                "name": "...",
                "artistName": "...",
                "albumName": "...",
                "durationInMillis": 123456,
                "isrc": "...",
                "genreNames": ["Pop", "Music"],
                "releaseDate": "YYYY-MM-DD",
                "composerName": "...",
                "contentRating": "explicit",
                "trackNumber": 1,
                "discNumber": 1,
                "artwork": {"url": "...{w}x{h}..."},
                "recordLabel": "...",
                "copyright": "...",
                "workName": "...",
                "movementName": "...",
                "movementNumber": 1,
                "movementCount": 4,
            },
            "relationships": {
                "credits": {"data": [...]},
                "lyrics": {"data": [...]},
                "albums": {"data": [...]},
            }
        }
        """
        attrs = data.get("attributes", {})
        relationships = data.get("relationships", {})

        # Parse release date
        release_date = attrs.get("releaseDate", "")
        year = None
        if release_date:
            try:
                year = int(release_date[:4])
            except (ValueError, IndexError):
                pass

        # Get genres (array, take first)
        genre_names = attrs.get("genreNames", [])
        genre = genre_names[0] if genre_names else None

        # Handle explicit flag
        content_rating = attrs.get("contentRating", "")
        explicit = content_rating == "explicit" if content_rating else None

        # Get artwork URL (replace size placeholders)
        artwork = attrs.get("artwork", {})
        artwork_url = artwork.get("url", "")
        if artwork_url:
            # Replace {w}x{h} with actual size
            artwork_url = artwork_url.replace("{w}", "1200").replace("{h}", "1200")

        # Get album info from relationships
        albums_data = relationships.get("albums", {}).get("data", [])
        album_id = albums_data[0].get("id") if albums_data else None

        # Extract credits/composer info
        composer = attrs.get("composerName")

        return ProviderTrack(
            service="apple_music",
            service_track_id=str(data.get("id")),
            title=attrs.get("name"),
            artist=attrs.get("artistName"),
            album=attrs.get("albumName"),
            album_id=album_id,
            duration_ms=attrs.get("durationInMillis"),
            isrc=attrs.get("isrc"),
            genre=genre,
            label=attrs.get("recordLabel"),
            copyright=attrs.get("copyright"),
            composer=composer,
            year=year,
            release_date=release_date,
            track_number=attrs.get("trackNumber"),
            disc_number=attrs.get("discNumber"),
            explicit=explicit,
            album_art_url=artwork_url,
            url=attrs.get("url"),
            preview_url=attrs.get("previews", [{}])[0].get(
                "url") if attrs.get("previews") else None,
            match_confidence=MatchConfidence.NONE,
            raw=data,
        )

    def _parse_credits(self, credits_data: List[Dict[str, Any]]) -> Optional[str]:
        """
        Parse credits from Apple Music relationship data.

        Args:
            credits_data: List of credit objects from relationships.credits.data

        Returns:
            Formatted credits string, or None
        """
        if not credits_data:
            return None

        credits_lines = []
        for credit in credits_data:
            attrs = credit.get("attributes", {})
            kind = attrs.get("kind", "")  # e.g., "performer"

            # Get credit-artists from nested relationships
            credit_artists = credit.get("relationships", {}).get(
                "credit-artists", {}).get("data", [])
            for artist in credit_artists:
                artist_attrs = artist.get("attributes", {})
                name = artist_attrs.get("name", "")
                roles = artist_attrs.get("roleNames", [])
                if name:
                    role_str = ", ".join(roles) if roles else kind
                    credits_lines.append(f"{role_str}: {name}")

        return "\n".join(credits_lines) if credits_lines else None
