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

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.beatport_normalize import normalize_beatport_track
from tagslut.metadata.genre_normalization import GenreNormalizer
from tagslut.metadata.models.types import (
    BeatportSeedExportStats,
    BeatportSeedRow,
    CONFIDENCE_NUMERIC,
    MatchConfidence,
    ProviderTrack,
    TidalBeatportMergedRow,
    TidalSeedRow,
)
from tagslut.metadata.providers.base import (
    AbstractProvider,
    RateLimitConfig,
    classify_match_confidence,
)

logger = logging.getLogger("tagslut.metadata.providers.beatport")

_CATALOG_TRACK_FILTER_PARAMS = {
    "artist_id",
    "artist_name",
    "available_worldwide",
    "bpm",
    "catalog_number",
    "change_date",
    "chord_type_id",
    "current_status",
    "dj_edits",
    "enabled",
    "encode_status",
    "encoded_date",
    "exclusive_date",
    "exclusive_period",
    "free_download_end_date",
    "free_download_start_date",
    "genre_enabled",
    "genre_id",
    "genre_name",
    "guid",
    "id",
    "is_available_for_streaming",
    "is_classic",
    "is_explicit",
    "is_hype",
    "isrc",
    "key_id",
    "key_name",
    "label_enabled",
    "label_id",
    "label_manager",
    "label_name",
    "label_name_exact",
    "mix_name",
    "name",
    "new_release_date",
    "order_by",
    "page",
    "per_page",
    "pre_order_date",
    "publish_date",
    "publish_status",
    "release_id",
    "release_name",
    "sale_type",
    "sub_genre_id",
    "supplier_id",
    "supplier_name",
    "track_number",
    "type",
    "type_id",
    "ugc_remixes",
    "was_ever_exclusive",
}

_SEARCH_TRACK_PARAMS = {
    "q",
    "count",
    "preorder",
    "from_publish_date",
    "to_publish_date",
    "from_release_date",
    "to_release_date",
    "genre_id",
    "genre_name",
    "mix_name",
    "from_bpm",
    "to_bpm",
    "key_name",
    "mix_name_weight",
    "label_name_weight",
    "dj_edits",
    "ugc_remixes",
    "dj_edits_and_ugc_remixes",
    "is_available_for_streaming",
}


class BeatportClientError(RuntimeError):
    """Base exception for official Beatport client failures."""


class BeatportAuthError(BeatportClientError):
    """Beatport auth was missing or rejected."""


class BeatportRateLimitError(BeatportClientError):
    """Beatport returned a rate-limit response."""


class BeatportNotFoundError(BeatportClientError):
    """Beatport resource was not found."""


class BeatportMalformedResponseError(BeatportClientError):
    """Beatport response body could not be parsed or was missing required keys."""


@dataclass(frozen=True)
class BeatportAuthConfig:
    """Credential bundle resolved from env/config for Beatport official APIs."""

    search_bearer_token: Optional[str] = None
    catalog_basic_username: Optional[str] = None
    catalog_basic_password: Optional[str] = None
    catalog_session_id: Optional[str] = None

    @property
    def has_search_auth(self) -> bool:
        return bool(self.search_bearer_token)

    @property
    def has_catalog_auth(self) -> bool:
        return bool(self.catalog_session_id or (self.catalog_basic_username and self.catalog_basic_password))


def _normalize_match_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()


def _parse_duration_ms(payload: Dict[str, Any]) -> Optional[int]:
    """Parse a duration from official Beatport payloads without guessing units."""
    length_ms = payload.get("length_ms")
    if isinstance(length_ms, int):
        return length_ms
    if isinstance(length_ms, float):
        return int(length_ms)

    length_text = payload.get("length")
    if not isinstance(length_text, str):
        return None

    parts = [part.strip() for part in length_text.split(":")]
    if not parts or not all(part.isdigit() for part in parts):
        return None

    total_seconds = 0
    for part in parts:
        total_seconds = (total_seconds * 60) + int(part)
    return total_seconds * 1000


def _extract_numeric_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return text
        match = re.search(r"/(\d+)/?$", text)
        if match:
            return match.group(1)
    return None


class BeatportApiClient:
    """Official Beatport API client using the locally checked-in OpenAPI contracts."""

    CATALOG_BASE_URL = "https://api.beatport.com"
    SEARCH_BASE_URL = "https://api.beatport.com"

    def __init__(self, provider: "BeatportProvider") -> None:
        self.provider = provider

    def _auth_config(self) -> BeatportAuthConfig:
        token = None
        if self.provider.token_manager is not None:
            token = self.provider.token_manager.ensure_valid_token("beatport")

        creds = self.provider.token_manager.get_credentials("beatport") if self.provider.token_manager else {}
        return BeatportAuthConfig(
            search_bearer_token=os.getenv("BEATPORT_ACCESS_TOKEN") or (token.access_token if token else None),
            catalog_basic_username=(
                os.getenv("BEATPORT_BASIC_AUTH_USERNAME")
                or os.getenv("BEATPORT_CLIENT_ID")
                or creds.get("client_id")
            ),
            catalog_basic_password=(
                os.getenv("BEATPORT_BASIC_AUTH_PASSWORD")
                or os.getenv("BEATPORT_CLIENT_SECRET")
                or creds.get("client_secret")
            ),
            catalog_session_id=(
                os.getenv("BEATPORT_SESSIONID")
                or os.getenv("BEATPORT_SESSION_ID")
                or (self.provider.token_manager._tokens.get("beatport", {}).get("sessionid") if self.provider.token_manager else None)  # type: ignore[attr-defined]
            ),
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        auth_kind: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        auth_config = self._auth_config()
        headers: Dict[str, str] = {"Accept": "application/json"}
        request_kwargs: Dict[str, Any] = {}

        if auth_kind == "search":
            if not auth_config.has_search_auth:
                raise BeatportAuthError("Beatport search requires a bearer token")
            headers["Authorization"] = f"Bearer {auth_config.search_bearer_token}"
        elif auth_kind == "catalog":
            if auth_config.catalog_session_id:
                headers["Cookie"] = f"sessionid={auth_config.catalog_session_id}"
            elif auth_config.catalog_basic_username and auth_config.catalog_basic_password:
                request_kwargs["auth"] = (
                    auth_config.catalog_basic_username,
                    auth_config.catalog_basic_password,
                )
            else:
                raise BeatportAuthError("Beatport catalog requires session cookie or basic auth credentials")
        else:
            raise BeatportClientError(f"Unsupported Beatport auth kind: {auth_kind}")

        while True:
            self.provider.rate_limiter.wait()
            try:
                response = self.provider.client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    **request_kwargs,
                )
            except httpx.HTTPError as exc:
                self.provider.rate_limiter.record_error()
                if self.provider.rate_limiter.should_retry:
                    continue
                raise BeatportClientError(str(exc)) from exc

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                self.provider.rate_limiter.record_error()
                logger.warning("beatport: rate limited, waiting %ds", retry_after)
                time.sleep(retry_after)
                if self.provider.rate_limiter.should_retry:
                    continue
                raise BeatportRateLimitError(f"Beatport rate limit exceeded for {url}")

            if response.status_code in (401, 403):
                self.provider.rate_limiter.record_error()
                raise BeatportAuthError(f"Beatport auth failed for {url} ({response.status_code})")

            if response.status_code == 404:
                self.provider.rate_limiter.record_success()
                raise BeatportNotFoundError(f"Beatport resource not found: {url}")

            if response.status_code >= 500:
                self.provider.rate_limiter.record_error()
                if self.provider.rate_limiter.should_retry:
                    continue
                raise BeatportClientError(f"Beatport server error {response.status_code} for {url}")

            if response.status_code >= 400:
                self.provider.rate_limiter.record_success()
                raise BeatportClientError(f"Beatport HTTP {response.status_code} for {url}")

            self.provider.rate_limiter.record_success()
            try:
                payload = response.json()
            except ValueError as exc:
                raise BeatportMalformedResponseError(f"Beatport returned malformed JSON for {url}") from exc
            if not isinstance(payload, dict):
                raise BeatportMalformedResponseError(f"Beatport returned non-object JSON for {url}")
            return payload

    def catalog_list_tracks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None and k in _CATALOG_TRACK_FILTER_PARAMS}
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/tracks/",
            auth_kind="catalog",
            params=clean_params,
        )

    def catalog_get_track(self, track_id: str | int) -> Dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/tracks/{track_id}/",
            auth_kind="catalog",
        )

    def catalog_get_release(self, release_id: str | int) -> Dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/releases/{release_id}/",
            auth_kind="catalog",
        )

    def catalog_list_genres(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/genres/",
            auth_kind="catalog",
            params=params,
        )

    def catalog_list_subgenres(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/sub-genres/",
            auth_kind="catalog",
            params=params,
        )

    def catalog_list_labels(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request_json(
            "GET",
            f"{self.CATALOG_BASE_URL}/v4/catalog/labels/",
            auth_kind="catalog",
            params=params,
        )

    def search_tracks(self, params: Dict[str, Any]) -> Dict[str, Any]:
        clean_params = {k: v for k, v in params.items() if v is not None and k in _SEARCH_TRACK_PARAMS}
        return self._request_json(
            "GET",
            f"{self.SEARCH_BASE_URL}/search/v1/tracks",
            auth_kind="search",
            params=clean_params,
        )


def _normalize_vendor_text(value: Any) -> Optional[str]:
    """Normalize spacing for vendor text without inventing canonical values."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return GenreNormalizer._normalize_spacing(text)


def _stringify_vendor_value(value: Any) -> Optional[str]:
    """Serialize vendor metadata values consistently for CSV output."""
    if value is None:
        return None
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return text or None


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

    def __init__(self, token_manager: TokenManager | None = None) -> None:
        super().__init__(token_manager)
        self._auth_available: bool | None = None
        self._build_id: str | None = None  # Next.js build ID cache
        self._api_client = BeatportApiClient(self)

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
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
            ),
            "x-nextjs-data": "1",
        }

    def _make_request_no_auth(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
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

    def _fetch_nextjs_release(self, release_id: int, slug: str) -> Optional[Dict]:  # type: ignore  # TODO: mypy-strict
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
                return response.json()  # type: ignore  # TODO: mypy-strict
            except Exception as e:
                logger.debug("Failed to parse Next.js release response: %s", e)
        return None

    def _fetch_release_web(self, release_id: int, slug: str) -> Optional[Dict]:  # type: ignore  # TODO: mypy-strict
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
            return json.loads(match.group(1))  # type: ignore  # TODO: mypy-strict
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

    def _fetch_nextjs_track(self, track_id: int, slug: str = "track") -> Optional[Dict[str, Any]]:
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
                page_props = data.get("pageProps", {})
                if isinstance(page_props, dict):
                    track = page_props.get("track")
                    if isinstance(track, dict):
                        return track
                return None
            except Exception as e:
                logger.debug("Failed to parse Next.js response: %s", e)

        return None

    def _search_web(self, query: str, limit: int = 10) -> List[Dict]:  # type: ignore  # TODO: mypy-strict
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

            return tracks[:limit]  # type: ignore  # TODO: mypy-strict

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
            return data.get("bp_track_id")  # type: ignore  # TODO: mypy-strict
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

        response = self._make_request_no_auth(
            "GET", url, params={"id": ids_csv}, headers={"Accept": "application/json"}
        )
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

    @staticmethod
    def _fallback_match_rank(match_confidence: MatchConfidence) -> int:
        rank = {
            MatchConfidence.EXACT: 4,
            MatchConfidence.STRONG: 3,
            MatchConfidence.MEDIUM: 2,
            MatchConfidence.WEAK: 1,
            MatchConfidence.NONE: 0,
        }
        return rank.get(match_confidence, 0)

    @staticmethod
    def _seed_row_from_provider_track(track: ProviderTrack) -> Optional[BeatportSeedRow]:
        """Convert a normalized Beatport track into a stable seed row."""
        if not track.service_track_id or not track.title or not track.artist or not track.url:
            return None

        raw = track.raw if isinstance(track.raw, dict) else {}
        release = raw.get("release")
        if not isinstance(release, dict):
            release = {}

        normalized = normalize_beatport_track(raw)
        return BeatportSeedRow(
            beatport_track_id=_stringify_vendor_value(normalized.service_track_id or track.service_track_id) or "",
            beatport_release_id=_stringify_vendor_value(
                normalized.release_id or release.get("id") or track.album_id
            ),
            beatport_url=_normalize_vendor_text(track.url or raw.get("url")) or "",
            title=track.title,
            artist=track.artist,
            isrc=track.isrc,
            beatport_bpm=_stringify_vendor_value(normalized.bpm if normalized.bpm is not None else track.bpm),
            beatport_key=_normalize_vendor_text(normalized.key or track.key),
            beatport_genre=_normalize_vendor_text(normalized.genre or track.genre),
            beatport_subgenre=_normalize_vendor_text(normalized.subgenre or track.sub_genre),
            beatport_label=_normalize_vendor_text(normalized.label_name or track.label),
            beatport_catalog_number=_normalize_vendor_text(normalized.catalog_number or track.catalog_number),
            beatport_upc=_normalize_vendor_text(
                release.get("upc") or raw.get("upc") or release.get("barcode") or raw.get("barcode")
            ),
            beatport_release_date=_normalize_vendor_text(
                normalized.publish_date
                or release.get("new_release_date")
                or release.get("publish_date")
                or track.release_date
            ),
        )

    def export_my_tracks_seed_rows(
        self,
        per_page: int = 100,
    ) -> tuple[List[BeatportSeedRow], BeatportSeedExportStats]:
        """Export stable seed rows from the authenticated Beatport library surface."""
        if not self._has_auth():
            raise RuntimeError("Beatport authentication is required for library seed export")

        page = 1
        seed_rows: List[BeatportSeedRow] = []
        stats = BeatportSeedExportStats()
        seen_row_keys: set[tuple[str, ...]] = set()

        while True:
            response = self._make_request(
                "GET",
                "https://api.beatport.com/v4/my/beatport/tracks/",
                params={"page": page, "per_page": per_page},
            )
            if response is None or response.status_code != 200:
                stats.pagination_stop_non_200 += 1
                logger.warning("Failed to fetch Beatport library page %d", page)
                break

            try:
                payload = response.json()
            except Exception as e:
                logger.error("Failed to parse Beatport library response: %s", e)
                break

            stats.pages_fetched += 1
            results = payload.get("results", [])
            if not isinstance(results, list) or not results:
                stats.pagination_stop_empty_page += 1
                break

            for item in results:
                if not isinstance(item, dict):
                    stats.rows_missing_required_fields += 1
                    continue
                track = self._normalize_track(item)
                seed_row = self._seed_row_from_provider_track(track)
                if seed_row is None:
                    stats.rows_missing_required_fields += 1
                    continue

                row_key = tuple(
                    getattr(seed_row, column) or ""
                    for column in (
                        "beatport_track_id",
                        "beatport_release_id",
                        "beatport_url",
                        "title",
                        "artist",
                        "isrc",
                    )
                )
                if row_key in seen_row_keys:
                    stats.duplicate_rows += 1
                    continue

                seen_row_keys.add(row_key)
                seed_rows.append(seed_row)
                stats.exported_rows += 1
                if not seed_row.isrc:
                    stats.missing_isrc_rows += 1

            if len(results) < per_page:
                stats.pagination_stop_short_page_no_next += 1
                break
            page += 1

        return seed_rows, stats

    def _select_best_title_artist_match(
        self,
        seed_row: TidalSeedRow,
    ) -> tuple[Optional[ProviderTrack], MatchConfidence, dict[str, int]]:
        """Select the strongest Beatport title/artist fallback match for a seed row."""
        candidates = self.search_by_artist_and_title(seed_row.artist, seed_row.title, limit=5)
        telemetry = {
            "ambiguous_fallback_rows": 1 if len(candidates) > 1 else 0,
            "fallback_equal_rank_ties": 0,
        }
        if not candidates:
            return None, MatchConfidence.NONE, telemetry

        scored_candidates: List[tuple[int, MatchConfidence, ProviderTrack]] = []
        for track in candidates:
            track.match_confidence = classify_match_confidence(
                seed_row.title,
                seed_row.artist,
                None,
                track,
            )
            rank = self._fallback_match_rank(track.match_confidence)
            scored_candidates.append((rank, track.match_confidence, track))

        if telemetry["ambiguous_fallback_rows"]:
            logger.info(
                "Beatport fallback ambiguity for '%s' - '%s': %d candidates, selecting highest rank",
                seed_row.artist,
                seed_row.title,
                len(candidates),
            )

        best_rank = max(rank for rank, _, _ in scored_candidates)
        if best_rank <= 0:
            return None, MatchConfidence.NONE, telemetry

        best_candidates = [
            (confidence, track)
            for rank, confidence, track in scored_candidates
            if rank == best_rank
        ]
        if len(best_candidates) > 1:
            telemetry["fallback_equal_rank_ties"] = 1
            logger.info(
                "Beatport fallback tie for '%s' - '%s': %d top-rank candidates, keeping first",
                seed_row.artist,
                seed_row.title,
                len(best_candidates),
            )

        best_confidence, best_track = best_candidates[0]
        return best_track, best_confidence, telemetry

    def _merged_row_from_match(
        self,
        seed_row: TidalSeedRow,
        match: Optional[ProviderTrack],
        match_method: str,
        match_confidence: MatchConfidence,
    ) -> TidalBeatportMergedRow:
        """Build the final merged CSV row while preserving TIDAL source fields."""
        merged = TidalBeatportMergedRow(
            tidal_playlist_id=seed_row.tidal_playlist_id,
            tidal_track_id=seed_row.tidal_track_id,
            tidal_url=seed_row.tidal_url,
            title=seed_row.title,
            artist=seed_row.artist,
            isrc=seed_row.isrc,
            match_method=match_method,
            match_confidence=match_confidence,
            last_synced_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )

        if match is None:
            return merged

        raw = match.raw if isinstance(match.raw, dict) else {}
        normalized = normalize_beatport_track(raw)
        release = raw.get("release")
        if not isinstance(release, dict):
            release = {}

        merged.beatport_track_id = _stringify_vendor_value(
            normalized.service_track_id or match.service_track_id
        )
        merged.beatport_release_id = _stringify_vendor_value(
            normalized.release_id or release.get("id") or match.album_id
        )
        merged.beatport_url = _normalize_vendor_text(match.url or raw.get("url"))
        merged.beatport_bpm = _stringify_vendor_value(normalized.bpm if normalized.bpm is not None else match.bpm)
        merged.beatport_key = _normalize_vendor_text(normalized.key or match.key)
        merged.beatport_genre = _normalize_vendor_text(normalized.genre or match.genre)
        merged.beatport_subgenre = _normalize_vendor_text(normalized.subgenre or match.sub_genre)
        merged.beatport_label = _normalize_vendor_text(normalized.label_name or match.label)
        merged.beatport_catalog_number = _normalize_vendor_text(
            normalized.catalog_number or match.catalog_number
        )
        merged.beatport_upc = _normalize_vendor_text(
            release.get("upc") or raw.get("upc") or release.get("barcode") or raw.get("barcode")
        )
        merged.beatport_release_date = _normalize_vendor_text(
            normalized.publish_date
            or release.get("new_release_date")
            or release.get("publish_date")
            or match.release_date
        )
        return merged

    def enrich_tidal_seed_row(
        self,
        seed_row: TidalSeedRow,
    ) -> tuple[TidalBeatportMergedRow, dict[str, int]]:
        """
        Enrich a TIDAL seed row using Beatport-only lookup.

        Lookup order is deterministic:
        1. ISRC
        2. title/artist fallback
        """
        telemetry = {
            "ambiguous_isrc_rows": 0,
            "ambiguous_fallback_rows": 0,
            "fallback_equal_rank_ties": 0,
        }
        if seed_row.isrc:
            isrc_matches = self.search_by_isrc(seed_row.isrc)
            if len(isrc_matches) > 1:
                telemetry["ambiguous_isrc_rows"] = 1
                logger.info(
                    "Beatport ISRC ambiguity for %s: %d candidates, keeping first",
                    seed_row.isrc,
                    len(isrc_matches),
                )
            if isrc_matches:
                return self._merged_row_from_match(seed_row, isrc_matches[0], "isrc", MatchConfidence.EXACT), telemetry

        fallback_match, fallback_confidence, fallback_telemetry = self._select_best_title_artist_match(seed_row)
        telemetry.update(fallback_telemetry)
        if fallback_match is not None:
            return (
                self._merged_row_from_match(
                    seed_row,
                    fallback_match,
                    "title_artist_fallback",
                    fallback_confidence,
                ),
                telemetry,
            )

        return self._merged_row_from_match(seed_row, None, "no_match", MatchConfidence.NONE), telemetry

    def _fetch_release_for_track(self, track_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        release = track_payload.get("release")
        release_id = None
        if isinstance(release, dict):
            release_id = release.get("id") or release.get("release_id")
        if release_id is None:
            release_id = _extract_numeric_id(release)
        if release_id is None:
            return None
        try:
            return self._api_client.catalog_get_release(release_id)
        except BeatportClientError as exc:
            logger.debug("Failed to hydrate Beatport release %s: %s", release_id, exc)
            return None

    def _build_track_payload(
        self,
        *,
        catalog_payload: Dict[str, Any],
        search_payload: Optional[Dict[str, Any]] = None,
        release_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = dict(catalog_payload)
        payload["_catalog"] = dict(catalog_payload)

        if search_payload:
            payload["_search"] = dict(search_payload)
            if not isinstance(payload.get("release"), dict) and isinstance(search_payload.get("release"), dict):
                payload["release"] = dict(search_payload["release"])
            if not isinstance(payload.get("label"), dict) and isinstance(search_payload.get("label"), dict):
                payload["label"] = dict(search_payload["label"])
            if not payload.get("artists") and isinstance(search_payload.get("artists"), list):
                payload["artists"] = list(search_payload["artists"])
            if not payload.get("genre") and search_payload.get("genre") is not None:
                payload["genre"] = search_payload.get("genre")
            if not payload.get("sub_genre") and search_payload.get("sub_genre") is not None:
                payload["sub_genre"] = search_payload.get("sub_genre")

        if release_payload:
            payload["_release"] = dict(release_payload)
            payload["release"] = dict(release_payload)
            if not isinstance(payload.get("label"), dict) and isinstance(release_payload.get("label"), dict):
                payload["label"] = dict(release_payload["label"])
            if not payload.get("catalog_number") and release_payload.get("catalog_number"):
                payload["catalog_number"] = release_payload.get("catalog_number")
            if not payload.get("upc") and release_payload.get("upc"):
                payload["upc"] = release_payload.get("upc")

        return payload

    def _provider_track_from_payload(
        self,
        payload: Dict[str, Any],
        *,
        confidence: MatchConfidence,
    ) -> ProviderTrack:
        track = self._normalize_track(payload)
        track.match_confidence = confidence
        return track

    @staticmethod
    def _search_query(title: str, artist: Optional[str] = None) -> str:
        parts = [part.strip() for part in [artist, title] if part and part.strip()]
        return " ".join(parts)

    @staticmethod
    def _rank_search_candidate(
        candidate: Dict[str, Any],
        *,
        title: str,
        artist: Optional[str],
        mix_name: Optional[str],
    ) -> tuple[int, int, float, int]:
        candidate_title = _normalize_match_text(
            str(candidate.get("track_name") or candidate.get("name") or "")
        )
        candidate_artist = _normalize_match_text(
            ", ".join(
                artist_obj.get("artist_name") or artist_obj.get("name") or ""
                for artist_obj in candidate.get("artists", [])
                if isinstance(artist_obj, dict)
            )
        )
        title_text = _normalize_match_text(title)
        artist_text = _normalize_match_text(artist)
        mix_text = _normalize_match_text(mix_name)
        candidate_mix = _normalize_match_text(str(candidate.get("mix_name") or ""))

        exact_title = int(candidate_title == title_text and bool(title_text))
        exact_artist = int(candidate_artist == artist_text and bool(artist_text))
        exact_mix = int(candidate_mix == mix_text and bool(mix_text))
        score = float(candidate.get("score") or 0.0)
        track_id = int(candidate.get("track_id") or candidate.get("id") or 0)

        # Deterministic ranking:
        # 1) exact title match
        # 2) exact artist match when artist was provided
        # 3) exact mix-name match when requested
        # 4) provider search score
        # 5) stable tie-break on track_id
        return (exact_title, exact_artist + exact_mix, score, -track_id)

    @staticmethod
    def _classify_text_search_confidence(
        track: ProviderTrack,
        *,
        title: str,
        artist: Optional[str],
        mix_name: Optional[str],
    ) -> MatchConfidence:
        confidence = classify_match_confidence(title, artist, None, track)
        if confidence != MatchConfidence.NONE:
            return confidence

        title_text = _normalize_match_text(title)
        artist_text = _normalize_match_text(artist)
        mix_text = _normalize_match_text(mix_name)

        track_title = _normalize_match_text(track.title)
        track_artist = _normalize_match_text(track.artist)
        track_mix = _normalize_match_text(track.mix_name)

        exact_title = bool(title_text) and track_title == title_text
        exact_artist = bool(artist_text) and track_artist == artist_text
        exact_mix = bool(mix_text) and track_mix == mix_text

        if exact_title and not artist_text:
            return MatchConfidence.MEDIUM
        if exact_title and exact_mix:
            return MatchConfidence.MEDIUM
        if exact_title or exact_artist or exact_mix:
            return MatchConfidence.WEAK
        return MatchConfidence.NONE

    def _legacy_text_search(
        self,
        *,
        title: str,
        artist: Optional[str],
        mix_name: Optional[str],
        limit: int,
    ) -> List[ProviderTrack]:
        query = self._search_query(title, artist)
        web_results = self._search_web(query, limit)
        if not web_results:
            return []

        ranked_candidates = sorted(
            [candidate for candidate in web_results if isinstance(candidate, dict)],
            key=lambda candidate: self._rank_search_candidate(
                candidate,
                title=title,
                artist=artist,
                mix_name=mix_name,
            ),
            reverse=True,
        )

        tracks: List[ProviderTrack] = []
        for candidate in ranked_candidates:
            try:
                track = self._normalize_track(candidate)
            except BeatportClientError as exc:
                logger.debug("Skipping malformed Beatport web-search candidate for %r: %s", query, exc)
                continue
            track.match_confidence = self._classify_text_search_confidence(
                track,
                title=title,
                artist=artist,
                mix_name=mix_name,
            )
            tracks.append(track)
        return tracks

    def search_track_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        """Official catalog exact-match lookup by ISRC."""
        try:
            payload = self._api_client.catalog_list_tracks({"isrc": isrc, "per_page": 10})
        except BeatportAuthError as exc:
            logger.warning("Beatport catalog auth unavailable for ISRC search: %s", exc)
            return []
        except BeatportClientError as exc:
            logger.warning("Beatport ISRC search failed for %s: %s", isrc, exc)
            return []

        results = payload.get("results")
        if not isinstance(results, list):
            logger.warning("Beatport catalog track list missing results array for ISRC %s", isrc)
            return []

        tracks: List[ProviderTrack] = []
        for item in results:
            if not isinstance(item, dict):
                logger.debug("Skipping malformed Beatport catalog ISRC item for %s", isrc)
                continue
            catalog_payload = dict(item)
            track_id = catalog_payload.get("id")
            if track_id is not None:
                try:
                    catalog_payload = self._api_client.catalog_get_track(track_id)
                except BeatportClientError as exc:
                    logger.debug("Beatport track hydrate failed for %s: %s", track_id, exc)
            release_payload = self._fetch_release_for_track(catalog_payload) or self._fetch_release_for_track(item)
            merged_payload = self._build_track_payload(
                catalog_payload=catalog_payload,
                search_payload=item,
                release_payload=release_payload,
            )
            tracks.append(
                self._provider_track_from_payload(
                    merged_payload,
                    confidence=MatchConfidence.EXACT,
                )
            )
        return tracks

    def search_track_by_text(
        self,
        title: str,
        artist: Optional[str] = None,
        **filters: Any,
    ) -> List[ProviderTrack]:
        """Official search-service candidate generation with catalog hydration."""
        mix_name = filters.get("mix_name")
        count = int(filters.get("count") or 10)
        fallback_limit = min(max(count, 1), 50)
        params = {
            "q": self._search_query(title, artist),
            "count": fallback_limit,
        }
        if mix_name:
            params["mix_name"] = mix_name
        for key, value in filters.items():
            if key in _SEARCH_TRACK_PARAMS and value is not None:
                params[key] = value

        try:
            payload = self._api_client.search_tracks(params)
        except BeatportAuthError as exc:
            logger.warning("Beatport search auth unavailable for text search: %s", exc)
            return self._legacy_text_search(
                title=title,
                artist=artist,
                mix_name=mix_name,
                limit=fallback_limit,
            )
        except BeatportClientError as exc:
            logger.warning("Beatport text search failed for %r: %s", params.get("q"), exc)
            return self._legacy_text_search(
                title=title,
                artist=artist,
                mix_name=mix_name,
                limit=fallback_limit,
            )

        data = payload.get("data")
        if not isinstance(data, list):
            logger.warning("Beatport search response missing data array for query %r", params.get("q"))
            return self._legacy_text_search(
                title=title,
                artist=artist,
                mix_name=mix_name,
                limit=fallback_limit,
            )

        ranked_candidates = sorted(
            [candidate for candidate in data if isinstance(candidate, dict)],
            key=lambda candidate: self._rank_search_candidate(
                candidate,
                title=title,
                artist=artist,
                mix_name=mix_name,
            ),
            reverse=True,
        )

        tracks: List[ProviderTrack] = []
        for candidate in ranked_candidates:
            track_id = candidate.get("track_id")
            catalog_payload: Dict[str, Any] = dict(candidate)
            if track_id is not None:
                try:
                    catalog_payload = self._api_client.catalog_get_track(track_id)
                except BeatportClientError as exc:
                    logger.debug("Beatport hydrate failed for search candidate %s: %s", track_id, exc)
            release_payload = self._fetch_release_for_track(catalog_payload) or self._fetch_release_for_track(candidate)
            merged_payload = self._build_track_payload(
                catalog_payload=catalog_payload,
                search_payload=candidate,
                release_payload=release_payload,
            )
            track = self._normalize_track(merged_payload)
            track.match_confidence = self._classify_text_search_confidence(
                track,
                title=title,
                artist=artist,
                mix_name=mix_name,
            )
            tracks.append(track)
        if tracks:
            return tracks
        return self._legacy_text_search(
            title=title,
            artist=artist,
            mix_name=mix_name,
            limit=fallback_limit,
        )

    def get_track_by_id(self, track_id: str | int) -> ProviderTrack:
        """Canonical catalog hydration by Beatport track ID."""
        catalog_payload = self._api_client.catalog_get_track(track_id)
        if "id" not in catalog_payload:
            raise BeatportMalformedResponseError("Beatport catalog track detail missing id")
        release_payload = self._fetch_release_for_track(catalog_payload)
        merged_payload = self._build_track_payload(
            catalog_payload=catalog_payload,
            release_payload=release_payload,
        )
        return self._provider_track_from_payload(merged_payload, confidence=MatchConfidence.EXACT)

    def get_genres(self) -> List[Dict[str, Any]]:
        payload = self._api_client.catalog_list_genres({"page": 1, "per_page": 200})
        results = payload.get("results")
        if not isinstance(results, list):
            raise BeatportMalformedResponseError("Beatport genres response missing results")
        return [item for item in results if isinstance(item, dict)]

    def get_subgenres(self) -> List[Dict[str, Any]]:
        payload = self._api_client.catalog_list_subgenres({"page": 1, "per_page": 200})
        results = payload.get("results")
        if not isinstance(results, list):
            raise BeatportMalformedResponseError("Beatport sub-genres response missing results")
        return [item for item in results if isinstance(item, dict)]

    def get_labels(self) -> List[Dict[str, Any]]:
        payload = self._api_client.catalog_list_labels({"page": 1, "per_page": 200})
        results = payload.get("results")
        if not isinstance(results, list):
            raise BeatportMalformedResponseError("Beatport labels response missing results")
        return [item for item in results if isinstance(item, dict)]

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        extracted_id = _extract_numeric_id(track_id)
        if extracted_id is not None:
            track_data = self._fetch_nextjs_track(int(extracted_id))
            if track_data:
                track = self._normalize_track(track_data)
                track.match_confidence = MatchConfidence.EXACT
                return track
        try:
            return self.get_track_by_id(track_id)
        except BeatportClientError as exc:
            logger.debug("Could not fetch Beatport track %s: %s", track_id, exc)
            return None

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        return self.search_track_by_isrc(isrc)

    def search_by_artist_and_title(
        self, artist: str, title: str, limit: int = 5
    ) -> List[ProviderTrack]:
        return self.search_track_by_text(title, artist=artist, count=limit)

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        return self.search_track_by_text(query, artist=None, count=limit)

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
        album_name = None
        album_id = None
        if isinstance(release, dict):
            album_name = release.get("name") or release.get("release_name")
            album_id = _extract_numeric_id(release.get("id") or release.get("release_id"))
        else:
            album_id = _extract_numeric_id(release)

        release_payload = data.get("_release")
        if isinstance(release_payload, dict):
            album_name = album_name or release_payload.get("name") or release_payload.get("release_name")
            album_id = album_id or _extract_numeric_id(
                release_payload.get("id") or release_payload.get("release_id")
            )

        # Handle publish_date / release_date
        publish_date = (
            data.get("publish_date")
            or data.get("release_date")
            or data.get("new_release_date")
            or ""
        )
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

        # Handle label: either top-level label, release.label, or hydrated release payload
        label = data.get("label")
        if not isinstance(label, dict) and isinstance(release, dict):
            label = release.get("label")
        if not isinstance(label, dict) and isinstance(release_payload, dict):
            label = release_payload.get("label")
        if isinstance(label, dict):
            label_name = label.get("name") or label.get("label_name")
        else:
            label_name = None

        # Handle duration from official catalog/list payloads without guessing search units.
        duration_ms = _parse_duration_ms(data)

        # Handle image
        image_url = (
            data.get("image", {}).get("uri") or
            data.get("track_image_uri") or
            (release.get("release_image_uri") if isinstance(release, dict) else None) or
            (
                release_payload.get("image", {}).get("uri")
                if isinstance(release_payload, dict) and isinstance(release_payload.get("image"), dict)
                else None
            )
        )

        # Catalog number from release
        catalog_number = data.get("catalog_number")
        if catalog_number is None and isinstance(release, dict):
            catalog_number = release.get("catalog_number")
        if catalog_number is None and isinstance(release_payload, dict):
            catalog_number = release_payload.get("catalog_number")

        # Track URL - build if not present
        slug = data.get("slug", "track")
        track_url = data.get("url") or f"https://www.beatport.com/track/{slug}/{track_id}"

        # Preview / waveform URLs
        preview_url = data.get("preview_url") or data.get("sample_url")
        waveform_url = data.get("waveform_url")

        if not title or not track_id:
            raise BeatportMalformedResponseError("Beatport track payload missing id or title")

        return ProviderTrack(
            service="beatport",
            service_track_id=str(track_id) if track_id else None,  # type: ignore  # TODO: mypy-strict
            title=title,
            artist=artist_name,
            album=album_name,
            album_id=album_id,
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
            track_number=data.get("track_number") or data.get("number"),
            match_confidence=MatchConfidence.NONE,  # Set by caller
            raw=data,
        )
