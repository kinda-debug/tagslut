"""
TIDAL API provider.

This provider supports:
- Track lookup by ID
- ISRC lookup
- Text search
- Stable playlist seed export (tidal-seed)
- Beatport seed enrichment (tidal-enrich)

Notes:
- For track/ISRC/search, we use TIDAL's v2 JSON:API (openapi.tidal.com/v2).
- For playlist seed export, we use the simpler v1 playlist tracks endpoint
  (api.tidal.com/v1) to keep payload handling stable and minimal.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse

import httpx

from tagslut.metadata.models.types import (
    BeatportSeedRow,
    BeatportTidalMergedRow,
    CONFIDENCE_NUMERIC,
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


class TidalProvider(AbstractProvider):
    """
    Tidal provider.

    v2 JSON:API endpoints (openapi.tidal.com/v2):
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
    V1_BASE_URL = "https://api.tidal.com/v1"
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
    def _media_tags_to_audio_quality(media_tags: Any) -> Optional[str]:
        if not isinstance(media_tags, list):
            return None
        tags = [str(tag) for tag in media_tags if tag]
        if not tags:
            return None
        for preferred in ("HIRES_LOSSLESS", "LOSSLESS", "DOLBY_ATMOS", "SONY_360RA"):
            if preferred in tags:
                return preferred
        return ",".join(tags)

    def _get_default_headers(self) -> Dict[str, str]:
        token = self._get_token()
        headers = {
            "Accept": "application/vnd.api+json",
        }
        if token and token.access_token:
            headers["Authorization"] = f"Bearer {token.access_token}"
        return headers

    def _make_request(self, *args, **kwargs):  # type: ignore[override]  # TODO: mypy-strict
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
        response = self._make_request("GET", url, params=params)  # type: ignore[arg-type]
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
            if not isinstance(identifier, dict):
                continue
            if isinstance(identifier.get("attributes"), dict):
                resolved = identifier
            else:
                resource_type = str(identifier.get("type") or "").strip()
                resource_id = str(identifier.get("id") or "").strip()
                resolved = included_index.get((resource_type, resource_id))
            if resolved is not None and isinstance(resolved, dict):
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
        if next_url.startswith(("http://", "https://")):
            return next_url
        if next_url.startswith("/"):
            return f"{self.BASE_URL}{next_url}"
        return f"{self.BASE_URL}/{next_url}"

    def _normalize_track(
        self,
        resource: Dict[str, Any],
        included_index: Optional[Dict[tuple[str, str], Dict[str, Any]]] = None,
    ) -> Optional[ProviderTrack]:
        if not isinstance(resource, dict):
            return None

        if "resource" in resource and isinstance(resource.get("resource"), dict):
            resource = resource.get("resource", {})

        attributes: Dict[str, Any]
        relationships: Dict[str, Any]
        resource_id: Any

        if "attributes" not in resource and "id" in resource and "title" in resource:
            attributes = resource  # already flattened
            relationships = {}
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
        album_attributes = (
            album.get("attributes")
            if isinstance(album, dict) and isinstance(album.get("attributes"), dict)
            else {}
        )
        album_name = album_attributes.get("title")
        album_id = str(album.get("id")) if isinstance(album, dict) and album.get("id") is not None else None
        release_date = album_attributes.get("releaseDate")

        duration_ms = self._parse_duration_ms(attributes.get("duration"))
        track_url = f"https://tidal.com/browse/track/{track_id}"

        return ProviderTrack(
            service="tidal",
            service_track_id=track_id,
            title=str(title),
            artist=artist_name,
            album=album_name,
            album_id=album_id,
            duration_ms=duration_ms,
            isrc=attributes.get("isrc"),
            release_date=release_date,
            bpm=attributes.get("bpm"),
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

    # Transport: v2 JSON:API — uses filter[isrc] on GET /tracks. Follows next-link pagination up to limit.
    def search_by_isrc(self, isrc: str, limit: int = 5) -> List[ProviderTrack]:
        next_url: Optional[str] = f"{self.BASE_URL}/tracks"
        params: Optional[Dict[str, Any]] = {
            "filter[isrc]": (isrc or "").strip(),
            "limit": min(int(limit), 50),
            "include": ["albums", "artists"],
        }
        results: List[ProviderTrack] = []
        while next_url and len(results) < limit:
            payload = self._request_json_document(
                next_url,
                params=params,
                failure_context=f"isrc {isrc}",
            )
            if payload is None:
                break
            included_index = self._build_included_index(payload)
            for item in self._extract_data_items(payload):
                if len(results) >= limit:
                    break
                track = self._normalize_track(item, included_index)
                if track is None:
                    continue
                if track.isrc and track.isrc.strip().upper() == (isrc or "").strip().upper():
                    track.match_confidence = MatchConfidence.EXACT
                    results.append(track)
            next_url = self._resolve_next_url(payload)
            params = None  # params only on first request; next_url already encodes them
        return results[:limit]

    # Transport: v2 JSON:API — text search via searchResults endpoint. No ISRC filter.
    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        encoded_query = quote((query or "").strip(), safe="")
        if not encoded_query:
            return []

        next_url = f"{self.BASE_URL}/searchResults/{encoded_query}/relationships/tracks"
        params: Optional[Dict[str, Any]] = {
            "include": ["tracks", "tracks.albums", "tracks.artists"],
            "explicitFilter": "INCLUDE",
            "limit": min(int(limit), 50),
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

                # Identifier might not include attributes; hydrate via fetch-by-id.
                track = self._fetch_track_provider_track(track_id)
                if track is None:
                    continue
                results.append(track)

            next_candidate = self._resolve_next_url(payload)
            next_url = next_candidate or ""
            params = None

        return results[:limit]

    # ---------------------------------------------------------------------
    # Beatport -> TIDAL enrichment (used by `tidal-enrich`)
    # ---------------------------------------------------------------------

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
                "TIDAL fallback tie for '%s' - '%s': %d top-rank candidates, keeping first",
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
        match_confidence: MatchConfidence,
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
            isrc_matches = self.search_by_isrc(seed_row.isrc, limit=5)
            if len(isrc_matches) > 1:
                telemetry["ambiguous_isrc_rows"] = 1
                logger.info(
                    "TIDAL ISRC ambiguity for %s: %d candidates, keeping first",
                    seed_row.isrc,
                    len(isrc_matches),
                )
            if isrc_matches:
                return self._merged_row_from_beatport_seed(seed_row, isrc_matches[0], "isrc", MatchConfidence.EXACT), telemetry

        fallback_match, fallback_confidence, fallback_telemetry = self._select_best_title_artist_match(seed_row)
        telemetry.update(fallback_telemetry)
        if fallback_match is not None:
            return (
                self._merged_row_from_beatport_seed(
                    seed_row,
                    fallback_match,
                    "title_artist_fallback",
                    fallback_confidence,
                ),
                telemetry,
            )

        return self._merged_row_from_beatport_seed(seed_row, None, "no_match", MatchConfidence.NONE), telemetry

    # ---------------------------------------------------------------------
    # TIDAL playlist seed export (used by `tidal-seed`)
    # ---------------------------------------------------------------------

    # Transport: v1 legacy — used only for playlist export. No ISRC capability.
    def _tidal_v1_get(self, endpoint: str, *, params: Dict[str, Any]) -> httpx.Response:
        token = self._get_token()
        if token is None or not token.access_token:
            raise RuntimeError("TIDAL token missing")
        merged = dict(params)
        if "countryCode" not in merged:
            merged["countryCode"] = self.COUNTRY_CODE
        return self.client.get(
            endpoint,
            params=merged,
            headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
        )

    @staticmethod
    def _join_names(items: Any) -> str:
        if not isinstance(items, list):
            return ""
        names: list[str] = []
        for item in items:
            if isinstance(item, dict):
                name = item.get("name")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
        return ", ".join(names)

    # v1 transport: legacy playlist export path. No ISRC. No migration without parity validation.
    def export_playlist_seed_rows(
        self,
        playlist_url_or_id: str,
    ) -> tuple[List[TidalSeedRow], TidalSeedExportStats]:
        playlist_id = self._parse_playlist_id(playlist_url_or_id)
        stats = TidalSeedExportStats(
            input_playlist=str(playlist_url_or_id or "").strip(),
            playlist_id=playlist_id or "",
            exported_rows=0,
            missing_isrc_rows=0,
            missing_required_rows=0,
            malformed_rows=0,
            duplicate_rows=0,
            pages=0,
            pagination_stop_short_page_no_next=0,
            pagination_stop_repeated_next=0,
        )
        if not playlist_id:
            stats.malformed_rows += 1
            return [], stats

        seed_rows: List[TidalSeedRow] = []
        seen_row_keys: set[tuple[str, str, str, str, str]] = set()

        # Fetch playlist title (optional; best-effort)
        playlist_title = ""
        try:
            meta = self._tidal_v1_get(f"{self.V1_BASE_URL}/playlists/{playlist_id}", params={})
            if meta.status_code == 200:
                data = meta.json()
                if isinstance(data, dict):
                    playlist_title = str(data.get("title") or "")
        except Exception:
            pass

        offset = 0
        limit = 100
        while True:
            stats.pages += 1
            resp = self._tidal_v1_get(
                f"{self.V1_BASE_URL}/playlists/{playlist_id}/tracks",
                params={"limit": limit, "offset": offset},
            )
            if resp.status_code != 200:
                logger.warning("TIDAL playlist tracks fetch failed: status=%s", resp.status_code)
                break

            payload = resp.json()
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not isinstance(items, list) or not items:
                stats.pagination_stop_short_page_no_next += 1
                break

            for item in items:
                if not isinstance(item, dict):
                    stats.malformed_rows += 1
                    continue
                track_id = str(item.get("id") or "").strip()
                title = str(item.get("title") or "").strip()
                artist = self._join_names(item.get("artists")) or ""
                isrc = str(item.get("isrc") or "").strip() or None
                url = f"https://tidal.com/browse/track/{track_id}" if track_id else ""

                if not track_id or not title or not artist or not url:
                    stats.missing_required_rows += 1
                    continue

                row_key = (playlist_id, track_id, url, title, artist)
                if row_key in seen_row_keys:
                    stats.duplicate_rows += 1
                    continue
                seen_row_keys.add(row_key)

                if not isrc:
                    stats.missing_isrc_rows += 1

                seed_rows.append(
                    TidalSeedRow(
                        tidal_playlist_id=playlist_id,
                        tidal_track_id=track_id,
                        tidal_url=url,
                        title=title,
                        artist=artist,
                        isrc=isrc,
                    )
                )
                stats.exported_rows += 1

            if len(items) < limit:
                stats.pagination_stop_short_page_no_next += 1
                break
            offset += len(items)

        if playlist_title and not stats.playlist_id:
            stats.playlist_id = playlist_title

        return seed_rows, stats
