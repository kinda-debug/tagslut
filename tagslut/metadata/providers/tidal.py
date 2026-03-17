"""
Tidal API provider.

Uses TIDAL's official v2 JSON:API endpoints for track lookup, search, and
playlist export while preserving the repo's existing provider surface.
"""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from tagslut.metadata.models.types import (
    BeatportSeedRow,
    BeatportTidalMergedRow,
    MatchConfidence,
    ProviderTrack,
    TidalSeedExportStats,
    TidalSeedRow,
)
from tagslut.metadata.providers.base import AbstractProvider, RateLimitConfig, classify_match_confidence

logger = logging.getLogger("tagslut.metadata.providers.tidal")

PLAYLIST_ID_PATTERN = re.compile(
    r"^(?:https?://[^/]+/(?:browse/)?playlist/)?(?P<playlist_id>[A-Za-z0-9-]+)(?:[/?#].*)?$"
)
_ISO_8601_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)
_FALLBACK_CONFIDENCE_NUMERIC = {
    MatchConfidence.EXACT: 0.95,
    MatchConfidence.STRONG: 0.85,
    MatchConfidence.MEDIUM: 0.70,
    MatchConfidence.WEAK: 0.55,
    MatchConfidence.NONE: 0.0,
}


class TidalProvider(AbstractProvider):
    """
    Tidal provider.

    Supports:
    - Track by ID: GET /tracks/{id}
    - Text search: GET /searchResults/{query}/relationships/tracks
    - ISRC search: GET /tracks?filter[isrc]={isrc}
    """

    name = "tidal"
    supports_isrc_search = True

    rate_limit_config = RateLimitConfig(
        min_delay=0.4,
        max_retries=3,
        base_backoff=2.0,
    )

    BASE_URL = "https://openapi.tidal.com/v2"
    COUNTRY_CODE = os.environ.get("TIDAL_COUNTRY_CODE", "US")

    @staticmethod
    def _parse_playlist_id(playlist_url_or_id: str) -> Optional[str]:
        candidate = (playlist_url_or_id or "").strip()
        if not candidate:
            return None
        match = PLAYLIST_ID_PATTERN.search(candidate)
        if not match:
            return None
        playlist_id = (match.group("playlist_id") or "").strip()
        return playlist_id or None

    @staticmethod
    def _parse_duration_ms(value: Any) -> Optional[int]:
        if isinstance(value, (int, float)):
            return int(float(value) * 1000)
        if not isinstance(value, str):
            return None
        match = _ISO_8601_DURATION_PATTERN.match(value.strip())
        if not match:
            return None
        parts = match.groupdict(default="0")
        total_seconds = (
            (int(parts["days"]) * 86400)
            + (int(parts["hours"]) * 3600)
            + (int(parts["minutes"]) * 60)
            + float(parts["seconds"])
        )
        return int(total_seconds * 1000)

    @staticmethod
    def _extract_data_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _build_included_index(payload: Dict[str, Any]) -> Dict[tuple[str, str], Dict[str, Any]]:
        included = payload.get("included")
        if not isinstance(included, list):
            return {}
        index: Dict[tuple[str, str], Dict[str, Any]] = {}
        for item in included:
            if not isinstance(item, dict):
                continue
            resource_type = str(item.get("type") or "").strip()
            resource_id = str(item.get("id") or "").strip()
            if resource_type and resource_id:
                index[(resource_type, resource_id)] = item
        return index

    @staticmethod
    def _resolve_resource(
        item: Dict[str, Any],
        included_index: Dict[tuple[str, str], Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        if isinstance(item.get("attributes"), dict):
            return item
        resource_type = str(item.get("type") or "").strip()
        resource_id = str(item.get("id") or "").strip()
        if not resource_type or not resource_id:
            return None
        return included_index.get((resource_type, resource_id))

    @staticmethod
    def _relationship_identifiers(resource: Dict[str, Any], relationship_name: str) -> List[Dict[str, Any]]:
        relationships = resource.get("relationships")
        if not isinstance(relationships, dict):
            return []
        relationship = relationships.get(relationship_name)
        if not isinstance(relationship, dict):
            return []
        data = relationship.get("data")
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def _related_resources(
        self,
        resource: Dict[str, Any],
        relationship_name: str,
        included_index: Dict[tuple[str, str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        resources: List[Dict[str, Any]] = []
        for identifier in self._relationship_identifiers(resource, relationship_name):
            resolved = self._resolve_resource(identifier, included_index)
            if resolved is not None:
                resources.append(resolved)
        return resources

    def _resolve_next_url(self, payload: Dict[str, Any]) -> Optional[str]:
        links = payload.get("links")
        if not isinstance(links, dict):
            return None
        next_link = links.get("next")
        if not isinstance(next_link, str) or not next_link.strip():
            return None
        next_url = next_link.strip()
        if next_url.startswith("http://") or next_url.startswith("https://"):
            return next_url
        if next_url.startswith("/"):
            return f"{self.BASE_URL}{next_url}"
        return f"{self.BASE_URL}/{next_url}"

    def _get_default_headers(self) -> Dict[str, str]:
        token = self._get_token()
        headers = {
            "Accept": "application/vnd.api+json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def _make_request(self, *args, **kwargs):  # type: ignore  # TODO: mypy-strict
        params = kwargs.get("params")
        if params is None:
            params = {}
        else:
            params = dict(params)
        if "countryCode" not in params:
            params["countryCode"] = self.COUNTRY_CODE
        kwargs["params"] = params
        return super()._make_request(*args, **kwargs)

    def _request_json_document(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        failure_context: str,
    ) -> Optional[Dict[str, Any]]:
        response = self._make_request("GET", url, params=params)  # type: ignore  # TODO: mypy-strict
        if response is None or response.status_code != 200:
            logger.warning("Failed to fetch TIDAL %s", failure_context)
            return None
        try:
            payload = response.json()
        except Exception as exc:
            logger.error("Failed to parse TIDAL %s response: %s", failure_context, exc)
            return None
        if not isinstance(payload, dict):
            logger.error("Failed to parse TIDAL %s response: expected object document", failure_context)
            return None
        return payload

    @staticmethod
    def _media_tags_to_audio_quality(media_tags: Any) -> Optional[str]:
        if not isinstance(media_tags, list):
            return None
        tags = [str(tag) for tag in media_tags if tag]
        if not tags:
            return None
        for preferred in ("HIRES_LOSSLESS", "LOSSLESS", "SONY_360RA", "DOLBY_ATMOS"):
            if preferred in tags:
                return preferred
        return ",".join(tags)

    def _normalize_track(
        self,
        resource: Dict[str, Any],
        included_index: Optional[Dict[tuple[str, str], Dict[str, Any]]] = None,
    ) -> Optional[ProviderTrack]:
        if not isinstance(resource, dict):
            return None

        if "resource" in resource and isinstance(resource.get("resource"), dict):
            resource = resource.get("resource", {})

        if "attributes" not in resource and "id" in resource and "title" in resource:
            attributes = resource
            relationships: Dict[str, Any] = {}
            resource_id = attributes.get("id")
        else:
            attributes = resource.get("attributes")
            if not isinstance(attributes, dict):
                return None
            relationships = resource.get("relationships") if isinstance(resource.get("relationships"), dict) else {}
            resource_id = resource.get("id")

        track_id = str(resource_id) if resource_id is not None else None
        title = attributes.get("title")
        if not track_id or not title:
            return None

        included_index = included_index or {}
        resource_wrapper = {
            "id": track_id,
            "attributes": attributes,
            "relationships": relationships,
            "type": resource.get("type", "tracks"),
        }

        artists = self._related_resources(resource_wrapper, "artists", included_index)
        artist_name = ", ".join(
            artist.get("attributes", {}).get("name", "")
            for artist in artists
            if isinstance(artist.get("attributes"), dict) and artist.get("attributes", {}).get("name")
        ) or None

        albums = self._related_resources(resource_wrapper, "albums", included_index)
        album = albums[0] if albums else None
        album_attributes = album.get("attributes") if isinstance(album, dict) and isinstance(album.get("attributes"), dict) else {}
        album_name = album_attributes.get("title")
        album_id = str(album.get("id")) if isinstance(album, dict) and album.get("id") is not None else None
        release_date = album_attributes.get("releaseDate")

        duration_ms = self._parse_duration_ms(attributes.get("duration"))

        key_value = attributes.get("key")
        key_scale = attributes.get("keyScale")
        canonical_key = None
        if key_value and key_scale:
            scale = str(key_scale).upper()
            if scale.startswith("MAJ"):
                canonical_key = f"{key_value} major"
            elif scale.startswith("MIN"):
                canonical_key = f"{key_value} minor"
            else:
                canonical_key = f"{key_value} {str(key_scale).lower()}"
        elif key_value:
            canonical_key = str(key_value)

        track_url = f"https://tidal.com/browse/track/{track_id}"

        return ProviderTrack(
            service="tidal",
            service_track_id=track_id,
            title=title,
            artist=artist_name,
            album=album_name,
            album_id=album_id,
            duration_ms=duration_ms,
            isrc=attributes.get("isrc"),
            release_date=release_date,
            bpm=attributes.get("bpm"),
            key=canonical_key,
            explicit=attributes.get("explicit"),
            audio_quality=self._media_tags_to_audio_quality(attributes.get("mediaTags")),
            copyright=attributes.get("copyright"),
            url=track_url,
            match_confidence=MatchConfidence.NONE,
            raw=resource,
        )

    def _fetch_track_provider_track(
        self,
        track_id: str,
        *,
        confidence: MatchConfidence = MatchConfidence.NONE,
    ) -> Optional[ProviderTrack]:
        payload = self._request_json_document(
            f"{self.BASE_URL}/tracks/{quote(str(track_id), safe='')}",
            params={"include": ["albums", "artists"]},
            failure_context=f"track {track_id}",
        )
        if payload is None:
            return None
        resources = self._extract_data_items(payload)
        if not resources:
            logger.warning("TIDAL track %s returned unusable data", track_id)
            return None
        track = self._normalize_track(resources[0], self._build_included_index(payload))
        if track is None:
            logger.warning("TIDAL track %s returned unusable data", track_id)
            return None
        track.match_confidence = confidence
        return track

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        return self._fetch_track_provider_track(track_id, confidence=MatchConfidence.EXACT)

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        encoded_query = quote((query or "").strip(), safe="")
        if not encoded_query:
            return []

        next_url = f"{self.BASE_URL}/searchResults/{encoded_query}/relationships/tracks"
        params: Optional[Dict[str, Any]] = {
            "include": ["tracks"],
            "explicitFilter": "INCLUDE",
        }
        seen_ids: set[str] = set()
        results: List[ProviderTrack] = []

        while next_url and len(results) < limit:
            payload = self._request_json_document(
                next_url,
                params=params,
                failure_context=f"search query {query!r}",
            )
            if payload is None:
                break

            included_index = self._build_included_index(payload)
            for identifier in self._extract_data_items(payload):
                if len(results) >= limit:
                    break
                track_id = str(identifier.get("id") or "").strip()
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                resource = self._resolve_resource(identifier, included_index)
                track = self._normalize_track(resource, included_index) if resource is not None else None
                if track is None or not track.artist:
                    track = self._fetch_track_provider_track(track_id)
                if track is not None:
                    results.append(track)

            next_url = self._resolve_next_url(payload)
            params = None

        return results[:limit]

    def search_by_isrc(self, isrc: str, limit: int = 5) -> List[ProviderTrack]:
        next_url = f"{self.BASE_URL}/tracks"
        params: Optional[Dict[str, Any]] = {
            "filter[isrc]": [isrc],
            "include": ["albums", "artists"],
        }
        results: List[ProviderTrack] = []
        seen_ids: set[str] = set()

        while next_url and len(results) < limit:
            payload = self._request_json_document(
                next_url,
                params=params,
                failure_context=f"ISRC search {isrc}",
            )
            if payload is None:
                break

            included_index = self._build_included_index(payload)
            for resource in self._extract_data_items(payload):
                if len(results) >= limit:
                    break
                track = self._normalize_track(resource, included_index)
                if track is None or track.service_track_id in seen_ids:
                    continue
                seen_ids.add(track.service_track_id)
                track.match_confidence = MatchConfidence.EXACT
                results.append(track)

            next_url = self._resolve_next_url(payload)
            params = None

        return results[:limit]

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

    def _track_from_playlist_item(
        self,
        item: Any,
        included_index: Dict[tuple[str, str], Dict[str, Any]],
    ) -> tuple[Optional[ProviderTrack], Optional[str]]:
        if not isinstance(item, dict):
            logger.debug("Skipping malformed TIDAL playlist item: not a dict")
            return None, "malformed"

        item_type = str(item.get("type") or "").strip()
        track_id = str(item.get("id") or "").strip()
        if item_type and item_type != "tracks":
            logger.debug("Skipping non-track TIDAL playlist item: type=%s id=%s", item_type, track_id)
            return None, "missing_required"
        if not track_id:
            logger.debug("Skipping TIDAL playlist item with missing id")
            return None, "missing_required"

        resource = self._resolve_resource(item, included_index)
        track = self._normalize_track(resource, included_index) if resource is not None else None
        if track is None or not track.artist:
            track = self._fetch_track_provider_track(track_id)
        if track is None:
            logger.debug("Skipping unusable TIDAL playlist item: missing normalized track")
            return None, "malformed"
        if not track.service_track_id or not track.title or not track.artist or not track.url:
            logger.debug(
                "Skipping TIDAL playlist item with missing required seed fields: id=%s title=%s artist=%s url=%s",
                track.service_track_id,
                track.title,
                track.artist,
                track.url,
            )
            return None, "missing_required"
        return track, None

    def export_playlist_seed_rows(
        self,
        playlist_url_or_id: str,
    ) -> tuple[List[TidalSeedRow], TidalSeedExportStats]:
        playlist_id = self._parse_playlist_id(playlist_url_or_id)
        if not playlist_id:
            logger.warning("Unable to parse TIDAL playlist identifier from: %s", playlist_url_or_id)
            return [], TidalSeedExportStats(playlist_id=playlist_url_or_id)

        seed_rows: List[TidalSeedRow] = []
        stats = TidalSeedExportStats(playlist_id=playlist_id)
        next_url = f"{self.BASE_URL}/playlists/{quote(playlist_id, safe='')}/relationships/items"
        params: Optional[Dict[str, Any]] = {"include": ["items"]}
        seen_next_urls: set[str] = set()
        seen_row_keys: set[tuple[str, ...]] = set()

        while next_url:
            response = self._make_request("GET", next_url, params=params)  # type: ignore  # TODO: mypy-strict
            if response is None or response.status_code != 200:
                stats.pagination_stop_non_200 += 1
                logger.warning("Failed to fetch TIDAL playlist %s", playlist_id)
                break

            try:
                payload = response.json()
            except Exception as exc:
                logger.error("Failed to parse TIDAL playlist response: %s", exc)
                break
            if not isinstance(payload, dict):
                logger.error("Failed to parse TIDAL playlist response: expected object document")
                break

            stats.pages_fetched += 1
            items = self._extract_data_items(payload)
            if not items:
                stats.pagination_stop_empty_page += 1
                break

            included_index = self._build_included_index(payload)
            for item in items:
                track, skip_reason = self._track_from_playlist_item(item, included_index)
                if track is None:
                    if skip_reason == "malformed":
                        stats.malformed_playlist_items += 1
                    elif skip_reason == "missing_required":
                        stats.rows_missing_required_fields += 1
                    continue

                seed_row = TidalSeedRow(
                    tidal_playlist_id=playlist_id,
                    tidal_track_id=track.service_track_id,
                    tidal_url=track.url,
                    title=track.title,
                    artist=track.artist,
                    isrc=track.isrc,
                )
                row_key = (
                    seed_row.tidal_playlist_id,
                    seed_row.tidal_track_id,
                    seed_row.tidal_url,
                    seed_row.title,
                    seed_row.artist,
                    seed_row.isrc or "",
                )
                if row_key in seen_row_keys:
                    stats.duplicate_rows += 1
                    logger.debug(
                        "Skipping duplicate TIDAL seed row: playlist=%s track=%s",
                        seed_row.tidal_playlist_id,
                        seed_row.tidal_track_id,
                    )
                    continue

                seen_row_keys.add(row_key)
                seed_rows.append(seed_row)
                stats.exported_rows += 1
                if not seed_row.isrc:
                    stats.missing_isrc_rows += 1

            next_candidate = self._resolve_next_url(payload)
            if next_candidate:
                if next_candidate in seen_next_urls:
                    stats.pagination_stop_repeated_next += 1
                    logger.warning("Stopping TIDAL playlist pagination due to repeated next link: %s", next_candidate)
                    break
                seen_next_urls.add(next_candidate)
                next_url = next_candidate
                params = None
                continue

            stats.pagination_stop_short_page_no_next += 1
            break

        return seed_rows, stats

    def _select_best_title_artist_match(
        self,
        seed_row: BeatportSeedRow,
    ) -> tuple[Optional[ProviderTrack], MatchConfidence, dict[str, int]]:
        candidates = self.search(f"{seed_row.artist} {seed_row.title}", limit=5)
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
                "Tidal fallback ambiguity for '%s' - '%s': %d candidates, selecting highest rank",
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
                "Tidal fallback tie for '%s' - '%s': %d top-rank candidates, keeping first",
                seed_row.artist,
                seed_row.title,
                len(best_candidates),
            )

        best_confidence, best_track = best_candidates[0]
        return best_track, best_confidence, telemetry

    def _merged_row_from_beatport_seed(
        self,
        seed_row: BeatportSeedRow,
        match: Optional[ProviderTrack],
        match_method: str,
        match_confidence: float,
    ) -> BeatportTidalMergedRow:
        merged = BeatportTidalMergedRow(
            beatport_track_id=seed_row.beatport_track_id,
            beatport_release_id=seed_row.beatport_release_id,
            beatport_url=seed_row.beatport_url,
            title=seed_row.title,
            artist=seed_row.artist,
            isrc=seed_row.isrc,
            beatport_bpm=seed_row.beatport_bpm,
            beatport_key=seed_row.beatport_key,
            beatport_genre=seed_row.beatport_genre,
            beatport_subgenre=seed_row.beatport_subgenre,
            beatport_label=seed_row.beatport_label,
            beatport_catalog_number=seed_row.beatport_catalog_number,
            beatport_upc=seed_row.beatport_upc,
            beatport_release_date=seed_row.beatport_release_date,
            match_method=match_method,
            match_confidence=match_confidence,
            last_synced_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        if match is None:
            return merged

        merged.tidal_track_id = match.service_track_id
        merged.tidal_url = match.url
        merged.tidal_title = match.title
        merged.tidal_artist = match.artist
        return merged

    def enrich_beatport_seed_row(
        self,
        seed_row: BeatportSeedRow,
    ) -> tuple[BeatportTidalMergedRow, dict[str, int]]:
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
                    "Tidal ISRC ambiguity for %s: %d candidates, keeping first",
                    seed_row.isrc,
                    len(isrc_matches),
                )
            if isrc_matches:
                return self._merged_row_from_beatport_seed(seed_row, isrc_matches[0], "isrc", 1.0), telemetry

        fallback_match, fallback_confidence, fallback_telemetry = self._select_best_title_artist_match(seed_row)
        telemetry.update(fallback_telemetry)
        if fallback_match is not None:
            return (
                self._merged_row_from_beatport_seed(
                    seed_row,
                    fallback_match,
                    "title_artist_fallback",
                    _FALLBACK_CONFIDENCE_NUMERIC.get(fallback_confidence, 0.0),
                ),
                telemetry,
            )

        return self._merged_row_from_beatport_seed(seed_row, None, "no_match", 0.0), telemetry
