"""
Beatport provider.

Beatport is a primary source for electronic music metadata, especially BPM, key, and genre.

This provider uses multiple methods (in order of preference):
1. V4 API (requires auth): /v4/catalog/tracks/ - best quality, supports ISRC search
2. Next.js data endpoints (unauthenticated, for track lookups by ID)
3. Web search with __NEXT_DATA__ scraping (fallback when no auth)
4. Beatsource migrator (unauthenticated, for ID mapping)

API Reference: https://api.beatport.com/v4/docs/
"""

import logging
import re
from typing import Optional, List, Dict, Any
import httpx
from urllib.parse import quote

from dedupe.metadata.models.types import ProviderTrack, MatchConfidence
from dedupe.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("dedupe.metadata.providers.beatport")


class BeatportProvider(AbstractProvider):
    """
    Beatport provider using multiple data sources.

    Primary method (with auth):
    - V4 API: /v4/catalog/tracks/ - ISRC search, artist+title filters

    Fallback methods (no auth needed):
    - Next.js data endpoints for track lookups by ID
    - Web scraping for search results
    - Beatsource migrator: /migrator/v1/track/
    """

    name = "beatport"
    supports_isrc_search = True  # Supported via /v4/catalog/tracks/?isrc=

    rate_limit_config = RateLimitConfig(
        min_delay=0.5,
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://api.beatport.com/v4/catalog"
    WEB_URL = "https://www.beatport.com"
    MIGRATOR_URL = "https://api.beatport.com/migrator/v1"

    def __init__(self, token_manager=None):
        super().__init__(token_manager)
        self._auth_available = None
        self._build_id = None  # Next.js build ID cache

    def _has_auth(self) -> bool:
        """Check if we have valid authentication."""
        if self._auth_available is None:
            if self.token_manager is None:
                self._auth_available = False
            else:
                token = self._get_token()
                self._auth_available = token is not None and bool(token.access_token)
        return self._auth_available

    def _get_default_headers(self) -> Dict[str, str]:
        """Get headers with Bearer token if available."""
        headers = {
            "Accept": "application/json",
        }
        if self.token_manager is not None:
            token = self._get_token()
            if token and token.access_token:
                headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def _get_web_headers(self) -> Dict[str, str]:
        """Get headers for web scraping."""
        return {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            "x-nextjs-data": "1",
        }

    def _make_request_no_auth(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[httpx.Response]:
        """
        Make a request without Authorization headers or token refresh.
        This mirrors the public Beatport API behavior used by MP3Tag.
        """
        all_headers = {"Accept": "application/json"}
        if headers:
            all_headers.update(headers)

        while True:
            self.rate_limiter.wait()
            try:
                response = self.client.request(
                    method,
                    url,
                    headers=all_headers,
                    params=params,
                    **kwargs,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning("%s: Rate limited, waiting %ds", self.name, retry_after)
                    time.sleep(retry_after)
                    self.rate_limiter.record_error()
                    if self.rate_limiter.should_retry:
                        continue
                    return None

                if response.status_code >= 500:
                    self.rate_limiter.record_error()
                    if self.rate_limiter.should_retry:
                        logger.warning(
                            "%s: Server error (%d), retrying...",
                            self.name,
                            response.status_code,
                        )
                        continue
                    return None

                self.rate_limiter.record_success()
                return response

            except httpx.HTTPError as e:
                logger.warning("%s: Request failed: %s", self.name, e)
                self.rate_limiter.record_error()
                if self.rate_limiter.should_retry:
                    continue
                return None

    def _get_build_id(self) -> Optional[str]:
        """Get current Next.js build ID from Beatport website."""
        if self._build_id:
            return self._build_id

        try:
            response = self._make_request_no_auth(
                "GET",
                self.WEB_URL,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
            )
            if response and response.status_code == 200:
                # Look for buildId in __NEXT_DATA__ or _next/static
                match = re.search(r'"buildId"\s*:\s*"([^"]+)"', response.text)
                if match:
                    self._build_id = match.group(1)
                    logger.debug("Found Beatport buildId: %s", self._build_id)
                    return self._build_id

                # Alternative: look in script src
                match = re.search(r'/_next/static/([^/]+)/_buildManifest\.js', response.text)
                if match:
                    self._build_id = match.group(1)
                    logger.debug("Found Beatport buildId from manifest: %s", self._build_id)
                    return self._build_id

        except Exception as e:
            logger.debug("Failed to get Beatport buildId: %s", e)

        return None

    def _fetch_nextjs_release(self, release_id: int, slug: str) -> Optional[Dict]:
        """Fetch release data via Next.js data endpoint (no auth needed)."""
        build_id = self._get_build_id()
        if not build_id:
            logger.debug("No buildId available for Next.js release fetch")
            return None

        url = f"{self.WEB_URL}/_next/data/{build_id}/en/release/{slug}/{release_id}.json"
        params = {"description": slug, "id": str(release_id)}
        response = self._make_request_no_auth("GET", url, params=params, headers=self._get_web_headers())
        if response and response.status_code == 200:
            try:
                return response.json()
            except Exception as e:
                logger.debug("Failed to parse Next.js release response: %s", e)
        return None

    def _fetch_release_web(self, release_id: int, slug: str) -> Optional[Dict]:
        """Fetch release HTML and parse __NEXT_DATA__ JSON (no auth needed)."""
        url = f"{self.WEB_URL}/release/{slug}/{release_id}"
        response = self._make_request_no_auth(
            "GET",
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"},
        )
        if not response or response.status_code != 200:
            return None
        try:
            import json
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', response.text)
            if not match:
                return None
            return json.loads(match.group(1))
        except Exception as e:
            logger.debug("Failed to parse Beatport release page: %s", e)
            return None

    def _extract_tracks_from_json(self, data: Any) -> List[Dict[str, Any]]:
        """Traverse a JSON object and extract track-like dictionaries."""
        tracks: List[Dict[str, Any]] = []
        stack: List[Any] = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if "tracks" in node and isinstance(node["tracks"], list):
                    for item in node["tracks"]:
                        if isinstance(item, dict) and (
                            "track_id" in item or "id" in item or "track_name" in item or "name" in item
                        ):
                            tracks.append(item)
                for value in node.values():
                    stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)
        # Deduplicate by track_id/id if present
        seen: set[str] = set()
        unique: List[Dict[str, Any]] = []
        for t in tracks:
            track_id = t.get("track_id") or t.get("id")
            key = str(track_id) if track_id is not None else None
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            unique.append(t)
        return unique

    def fetch_release_tracks(self, release_id: str, slug: Optional[str] = None) -> List[ProviderTrack]:
        """
        Fetch tracks for a Beatport release by ID/slug.

        Tries Next.js data, then HTML __NEXT_DATA__ parsing, then API (if auth).
        """
        slug = slug or "release"
        tracks: List[ProviderTrack] = []

        data = self._fetch_nextjs_release(int(release_id), slug)
        if data:
            track_objs = self._extract_tracks_from_json(data)
            if track_objs:
                return [self._normalize_track(t) for t in track_objs]

        data = self._fetch_release_web(int(release_id), slug)
        if data:
            track_objs = self._extract_tracks_from_json(data)
            if track_objs:
                return [self._normalize_track(t) for t in track_objs]

        if self._has_auth():
            url = f"{self.BASE_URL}/tracks/"
            params = {"release_id": release_id, "per_page": 100}
            response = self._make_request("GET", url, params=params)
            if response and response.status_code == 200:
                try:
                    payload = response.json()
                    results = payload.get("results", [])
                    if results:
                        return [self._normalize_track(t) for t in results]
                except Exception as e:
                    logger.debug("Failed to parse Beatport API release tracks: %s", e)

        return tracks
    def _fetch_nextjs_track(self, track_id: int, slug: str = "track") -> Optional[Dict]:
        """Fetch track data via Next.js data endpoint (no auth needed)."""
        build_id = self._get_build_id()
        if not build_id:
            logger.debug("No buildId available for Next.js fetch")
            return None

        url = f"{self.WEB_URL}/_next/data/{build_id}/en/track/{slug}/{track_id}.json"
        params = {"description": slug, "id": str(track_id)}

        response = self._make_request_no_auth("GET", url, params=params, headers=self._get_web_headers())
        if response and response.status_code == 200:
            try:
                data = response.json()
                return data.get("pageProps", {}).get("track")
            except Exception as e:
                logger.debug("Failed to parse Next.js response: %s", e)

        return None

    def _search_web(self, query: str, limit: int = 10) -> List[Dict]:
        """Search Beatport via web and extract results from __NEXT_DATA__."""
        encoded_query = quote(query)
        url = f"{self.WEB_URL}/search?q={encoded_query}"

        response = self._make_request_no_auth(
            "GET", url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}
        )

        if not response or response.status_code != 200:
            return []

        try:
            # Extract __NEXT_DATA__ JSON from the page
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>([^<]+)</script>', response.text)
            if not match:
                return []

            import json
            data = json.loads(match.group(1))

            # Data is in dehydratedState.queries[0].state.data.tracks.data
            queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
            if not queries:
                return []

            query_data = queries[0].get("state", {}).get("data", {})
            tracks_data = query_data.get("tracks", {})

            if isinstance(tracks_data, dict):
                tracks = tracks_data.get("data", [])
            else:
                tracks = tracks_data if isinstance(tracks_data, list) else []

            return tracks[:limit]

        except Exception as e:
            logger.debug("Failed to parse Beatport search page: %s", e)
            return []

    def map_beatsource_to_beatport(self, bs_track_id: int) -> Optional[int]:
        """
        Map a Beatsource track ID to Beatport track ID.

        This endpoint requires NO authentication.

        Args:
            bs_track_id: Beatsource track ID

        Returns:
            Beatport track ID, or None if not found
        """
        url = f"{self.MIGRATOR_URL}/track/{bs_track_id}"

        response = self._make_request_no_auth("GET", url, headers={"Accept": "application/json"})
        if response is None:
            return None

        if response.status_code == 404:
            logger.debug("No Beatport mapping for Beatsource track %s", bs_track_id)
            return None

        if response.status_code != 200:
            logger.warning("Beatsource mapping failed for %s: %s", bs_track_id, response.status_code)
            return None

        try:
            data = response.json()
            return data.get("bp_track_id")
        except Exception as e:
            logger.error("Failed to parse Beatsource mapping response: %s", e)
            return None

    def map_beatsource_bulk(self, bs_track_ids: List[int]) -> Dict[int, Optional[int]]:
        """
        Map multiple Beatsource track IDs to Beatport track IDs.

        This endpoint requires NO authentication.

        Args:
            bs_track_ids: List of Beatsource track IDs

        Returns:
            Dict mapping bs_track_id -> bp_track_id (or None if not found)
        """
        if not bs_track_ids:
            return {}

        ids_csv = ",".join(str(i) for i in bs_track_ids)
        url = f"{self.MIGRATOR_URL}/track/bulk"

        response = self._make_request_no_auth("GET", url, params={"id": ids_csv}, headers={"Accept": "application/json"})
        if response is None or response.status_code != 200:
            logger.warning("Bulk Beatsource mapping failed")
            return {i: None for i in bs_track_ids}

        try:
            data = response.json()
            result = {}
            for mapping in data:
                bs_id = mapping.get("bs_track_id")
                bp_id = mapping.get("bp_track_id")
                if bs_id is not None:
                    result[bs_id] = bp_id
            # Fill in None for any IDs not in response
            for bs_id in bs_track_ids:
                if bs_id not in result:
                    result[bs_id] = None
            return result
        except Exception as e:
            logger.error("Failed to parse bulk mapping response: %s", e)
            return {i: None for i in bs_track_ids}

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        """
        Fetch track by Beatport ID.

        Tries Next.js data endpoint first (no auth), falls back to API.

        Args:
            track_id: Beatport track ID (e.g., "12345")

        Returns:
            ProviderTrack with match_confidence=EXACT, or None
        """
        # Method 1: Try Next.js data endpoint (no auth needed)
        track_data = self._fetch_nextjs_track(int(track_id))
        if track_data:
            track = self._normalize_track(track_data)
            track.match_confidence = MatchConfidence.EXACT
            return track

        # Method 2: Try API if we have auth
        if self._has_auth():
            url = f"{self.BASE_URL}/tracks/{track_id}/"
            response = self._make_request("GET", url)
            if response and response.status_code == 200:
                try:
                    data = response.json()
                    track = self._normalize_track(data)
                    track.match_confidence = MatchConfidence.EXACT
                    return track
                except Exception as e:
                    logger.error("Failed to parse Beatport API response: %s", e)

        logger.debug("Could not fetch Beatport track %s", track_id)
        return None

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """
        Search for a track by ISRC using the authenticated API.

        Args:
            isrc: International Standard Recording Code

        Returns:
            List of ProviderTrack with match_confidence=EXACT
        """
        url = f"{self.BASE_URL}/tracks/"
        params = {
            "isrc": isrc,
            "per_page": 5,
        }

        # First try public (no-auth) API behavior (matches MP3Tag usage)
        response = self._make_request_no_auth("GET", url, params=params)
        if response and response.status_code == 200:
            try:
                data = response.json()
                results = data.get("results", [])
                tracks = []
                for item in results:
                    track = self._normalize_track(item)
                    track.match_confidence = MatchConfidence.EXACT
                    tracks.append(track)
                return tracks
            except Exception as e:
                logger.error("Failed to parse Beatport ISRC response (no-auth): %s", e)

        # Fall back to auth (if configured) for any cases where public endpoint fails
        if not self._has_auth():
            return []

        response = self._make_request("GET", url, params=params)
        if response and response.status_code == 200:
            try:
                data = response.json()
                results = data.get("results", [])
                tracks = []
                for item in results:
                    track = self._normalize_track(item)
                    track.match_confidence = MatchConfidence.EXACT
                    tracks.append(track)
                return tracks
            except Exception as e:
                logger.error("Failed to parse Beatport ISRC search response: %s", e)

        return []

    def search_by_artist_and_title(
        self, artist: str, title: str, limit: int = 5
    ) -> List[ProviderTrack]:
        """
        Search for tracks using both artist and title filters (authenticated API).

        This gives more precise results than a combined text search.

        Args:
            artist: Artist name
            title: Track title
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        if not self._has_auth():
            # Fall back to combined text search
            return self.search(f"{artist} {title}", limit)

        url = f"{self.BASE_URL}/tracks/"
        params = {
            "artist_name": artist,
            "name": title,
            "per_page": min(limit, 50),
        }

        response = self._make_request("GET", url, params=params)
        if response and response.status_code == 200:
            try:
                data = response.json()
                results = data.get("results", [])
                if results:
                    return [self._normalize_track(t) for t in results]
            except Exception as e:
                logger.error("Failed to parse Beatport artist+title search: %s", e)

        # Fall back to combined text search via web
        return self.search(f"{artist} {title}", limit)

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        """
        Search for tracks by text query.

        Prefers authenticated API (better results), falls back to web scraping.

        Args:
            query: Search query (e.g., "artist title")
            limit: Maximum results

        Returns:
            List of ProviderTrack objects
        """
        # Method 1: Try authenticated API (better filtering and results)
        if self._has_auth():
            url = f"{self.BASE_URL}/tracks/"
            params = {
                "name": query,
                "per_page": min(limit, 50),
            }

            response = self._make_request("GET", url, params=params)
            if response and response.status_code == 200:
                try:
                    data = response.json()
                    results = data.get("results", [])
                    if results:
                        return [self._normalize_track(t) for t in results]
                except Exception as e:
                    logger.error("Failed to parse Beatport API search response: %s", e)

        # Method 2: Fall back to web scraping (no auth needed)
        web_results = self._search_web(query, limit)
        if web_results:
            return [self._normalize_track(t) for t in web_results]

        logger.debug("Beatport search returned no results for: %s", query)
        return []

    def _normalize_track(self, data: Dict[str, Any]) -> ProviderTrack:
        """
        Normalize Beatport track object to ProviderTrack.

        Handles two formats:
        1. Next.js track endpoint (id, name, artists[].name, length_ms, key.name)
        2. Search results (track_id, track_name, artists[].artist_name, length, key_name)
        """
        # Handle different ID field names
        track_id = data.get("id") or data.get("track_id")

        # Handle different title field names
        title = data.get("name") or data.get("track_name")
        mix_name = data.get("mix_name")
        if mix_name and mix_name not in ("Original Mix", "Main Mix"):
            title = f"{title} ({mix_name})" if title else mix_name

        # Handle different artist structures
        artists = data.get("artists", [])
        if artists:
            # Check which format: {name: ...} or {artist_name: ...}
            if "name" in artists[0]:
                artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name"))
            else:
                artist_name = ", ".join(a.get("artist_name", "") for a in artists if a.get("artist_name"))
        else:
            artist_name = None

        # Handle release/album
        release = data.get("release", {})
        album_name = release.get("name") or release.get("release_name")

        # Handle publish_date
        publish_date = data.get("publish_date", "")
        year = None
        if publish_date:
            try:
                year = int(str(publish_date)[:4])
            except (ValueError, IndexError):
                pass

        # Handle key: either {name: ...} or key_name field
        key = data.get("key")
        if isinstance(key, dict):
            key_name = key.get("name")
        else:
            key_name = data.get("key_name")

        # Handle genre: {name: ...} or [{genre_name: ...}] or genre_name
        genre = data.get("genre")
        if isinstance(genre, dict):
            genre_name = genre.get("name") or genre.get("genre_name")
        elif isinstance(genre, list) and genre:
            genre_name = genre[0].get("genre_name") or genre[0].get("name")
        else:
            genre_name = None

        # Handle sub_genre
        sub_genre = data.get("sub_genre")
        if isinstance(sub_genre, dict):
            sub_genre_name = sub_genre.get("name") or sub_genre.get("sub_genre_name")
        else:
            sub_genre_name = None

        # Handle label: either {name: ...} or label.label_name
        label = data.get("label")
        if isinstance(label, dict):
            label_name = label.get("name") or label.get("label_name")
        else:
            label_name = None

        # Handle duration: length_ms (Next.js) or length (search, already in ms)
        duration_ms = data.get("length_ms") or data.get("length")

        # Handle image
        image_url = (
            data.get("image", {}).get("uri") or
            data.get("track_image_uri") or
            release.get("release_image_uri")
        )

        # Catalog number from release
        catalog_number = release.get("catalog_number")

        # Track URL - build if not present
        slug = data.get("slug", "track")
        track_url = data.get("url") or f"https://www.beatport.com/track/{slug}/{track_id}"

        # Preview / waveform URLs
        preview_url = data.get("preview_url") or data.get("sample_url")
        waveform_url = data.get("waveform_url")

        return ProviderTrack(
            service="beatport",
            service_track_id=str(track_id) if track_id else None,
            title=title,
            artist=artist_name,
            album=album_name,
            album_id=str(release.get("id")) if release.get("id") else None,
            duration_ms=duration_ms,
            isrc=data.get("isrc"),
            bpm=data.get("bpm"),
            key=key_name,
            genre=genre_name,
            sub_genre=sub_genre_name,
            label=label_name,
            catalog_number=catalog_number,
            mix_name=mix_name,
            year=year,
            release_date=publish_date,
            album_art_url=image_url,
            url=track_url,
            preview_url=preview_url,
            waveform_url=waveform_url,
            track_number=data.get("track_number"),
            match_confidence=MatchConfidence.NONE,  # Set by caller
            raw=data,
        )
