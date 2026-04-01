"""Qobuz metadata provider."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tagslut.metadata.capabilities import Capability
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig

logger = logging.getLogger("tagslut.metadata.providers.qobuz")


class QobuzProvider(AbstractProvider):
    name = "qobuz"
    supports_isrc_search = True
    capabilities = {
        Capability.METADATA_FETCH_TRACK_BY_ID,
        Capability.METADATA_SEARCH_BY_ISRC,
        Capability.METADATA_SEARCH_BY_TEXT,
        Capability.METADATA_FETCH_ARTWORK,
    }
    rate_limit_config = RateLimitConfig(min_delay=0.5, max_retries=3)
    BASE_URL = "https://www.qobuz.com/api.json/0.2"

    def _ensure_credentials(self) -> bool:
        """
        Ensure Qobuz credentials are present.
        Returns True if credentials are available, False otherwise.
        """
        if self.token_manager is None:
            return False

        app_id, app_secret = self.token_manager.get_qobuz_app_credentials()
        user_auth_token = self.token_manager.ensure_qobuz_token()
        if app_id and app_secret and user_auth_token:
            return True

        return False

    def _get_default_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token_manager is None:
            return headers

        app_id, _app_secret = self.token_manager.get_qobuz_app_credentials()
        if app_id:
            headers["X-App-Id"] = app_id

        user_auth_token = self.token_manager.ensure_qobuz_token()
        if user_auth_token:
            headers["X-User-Auth-Token"] = user_auth_token

        return headers

    def _get_app_id_and_token(self) -> tuple[Optional[str], Optional[str]]:
        if self.token_manager is None:
            return (None, None)
        app_id, _app_secret = self.token_manager.get_qobuz_app_credentials()
        user_auth_token = self.token_manager.ensure_qobuz_token()
        return (app_id, user_auth_token)

    def _is_invalid_app_secret_error(self, response) -> bool:  # type: ignore  # TODO: mypy-strict
        if response is None or response.status_code != 400:
            return False
        try:
            text = response.text or ""
        except Exception:
            text = ""
        return "InvalidAppSecretError" in text

    def _request_json(self, path: str, *, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}{path}"
        response = self._make_request("GET", url, params=params)
        if response is None:
            return None
        if self._is_invalid_app_secret_error(response):
            logger.error("qobuz: InvalidAppSecretError from API (check extracted credentials)")
            return None
        if response.status_code != 200:
            logger.warning("qobuz: request failed (%d) url=%s", response.status_code, url)
            return None
        try:
            data = response.json()
        except Exception as e:
            logger.warning("qobuz: invalid JSON response (%s) url=%s", e, url)
            return None
        return data if isinstance(data, dict) else None

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        if not self._ensure_credentials():
            return None
        app_id, user_auth_token = self._get_app_id_and_token()

        data = self._request_json(
            "/track/get",
            params={
                "track_id": track_id,
                "app_id": app_id,
            },
        )
        if not data:
            return None
        track = self._normalize_track(data)
        track.match_confidence = MatchConfidence.EXACT
        return track

    def search_by_isrc(self, isrc: str) -> List[ProviderTrack]:
        if not self._ensure_credentials():
            return []
        app_id, user_auth_token = self._get_app_id_and_token()

        data = self._request_json(
            "/track/search",
            params={
                "query": isrc,
                "app_id": app_id,
                "limit": 5,
            },
        )
        if not data:
            return []

        tracks = data.get("tracks") if isinstance(data, dict) else None
        items = tracks.get("items") if isinstance(tracks, dict) else None
        items = items if isinstance(items, list) else []

        out: List[ProviderTrack] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            raw_isrc = raw.get("isrc")
            if not raw_isrc or str(raw_isrc).upper() != isrc.upper():
                continue
            t = self._normalize_track(raw)
            t.match_confidence = MatchConfidence.EXACT
            out.append(t)
        return out

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        if not self._ensure_credentials():
            return []
        app_id, user_auth_token = self._get_app_id_and_token()

        data = self._request_json(
            "/track/search",
            params={
                "query": query,
                "app_id": app_id,
                "limit": limit,
            },
        )
        if not data:
            return []

        tracks = data.get("tracks") if isinstance(data, dict) else None
        items = tracks.get("items") if isinstance(tracks, dict) else None
        items = items if isinstance(items, list) else []

        out: List[ProviderTrack] = []
        for raw in items:
            if not isinstance(raw, dict):
                continue
            out.append(self._normalize_track(raw))
        return out

    def _normalize_track(self, raw: Dict[str, Any]) -> ProviderTrack:
        track_id = raw.get("id")
        track_id_str = str(track_id) if track_id is not None else ""

        performer = raw.get("performer") if isinstance(raw.get("performer"), dict) else {}
        artist = raw.get("artist") if isinstance(raw.get("artist"), dict) else {}
        artist_name = performer.get("name") or artist.get("name")

        album = raw.get("album") if isinstance(raw.get("album"), dict) else {}
        label = album.get("label") if isinstance(album.get("label"), dict) else {}
        image = album.get("image") if isinstance(album.get("image"), dict) else {}
        # Genre lives on the album object: album.genre.name or album.genres_list[0]
        album_genre_obj = album.get("genre") if isinstance(album.get("genre"), dict) else {}
        album_genres_list = album.get("genres_list") if isinstance(album.get("genres_list"), list) else []
        genre_name: Optional[str] = (
            album_genre_obj.get("name")
            or (album_genres_list[0] if album_genres_list else None)
            or raw.get("genre")  # fallback: track-level genre if ever present
        )

        duration = raw.get("duration")
        duration_ms: Optional[int] = None
        if isinstance(duration, int):
            duration_ms = duration * 1000

        parental_warning = raw.get("parental_warning")
        explicit: Optional[bool] = None
        if parental_warning is not None:
            explicit = bool(parental_warning)

        composer = raw.get("composer") if isinstance(raw.get("composer"), dict) else {}

        track = ProviderTrack(
            service="qobuz",
            service_track_id=track_id_str,
            title=raw.get("title"),
            artist=artist_name,
            album=album.get("title"),
            album_id=str(album.get("id")) if album.get("id") is not None else None,
            isrc=raw.get("isrc"),
            url=f"https://open.qobuz.com/track/{track_id_str}" if track_id_str else None,
            duration_ms=duration_ms,
            track_number=raw.get("track_number") if isinstance(raw.get("track_number"), int) else None,
            release_date=album.get("release_date_original"),
            label=label.get("name"),
            genre=genre_name,
            version=raw.get("version"),
            explicit=explicit,
            album_art_url=image.get("large"),
            composer=composer.get("name"),
            match_confidence=MatchConfidence.NONE,
            raw=dict(raw),
        )
        return track
