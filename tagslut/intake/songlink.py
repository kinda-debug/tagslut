from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

ODESLI_API = "https://api.song.link/v1-alpha.1/links"
REQUEST_DELAY = 6.5  # seconds — conservative for 10 req/min hard limit


def _extract_ids(payload: object) -> dict[str, str | None] | None:
    if not isinstance(payload, dict):
        return None
    entities = payload.get("entitiesByUniqueId")
    if not isinstance(entities, dict):
        return None

    tidal_id: str | None = None
    qobuz_id: str | None = None
    isrc: str | None = None

    for key, entity in entities.items():
        key_text = str(key or "")
        if key_text.startswith("TIDAL_SONG::") and tidal_id is None:
            candidate = key_text.split("::", 1)[-1].strip()
            if candidate:
                tidal_id = candidate
        elif key_text.startswith("QOBUZ_SONG::") and qobuz_id is None:
            candidate = key_text.split("::", 1)[-1].strip()
            if candidate:
                qobuz_id = candidate

        if isrc is None and isinstance(entity, dict):
            candidate = str(entity.get("isrc") or "").strip()
            if candidate:
                isrc = candidate

    if not tidal_id:
        return None
    return {"tidal_id": tidal_id, "qobuz_id": qobuz_id, "isrc": isrc}


def resolve_spotify_to_tidal(spotify_url: str) -> dict[str, str | None] | None:
    """
    Resolve a Spotify track URL to platform IDs via song.link.
    Returns dict with keys: tidal_id, qobuz_id, isrc (all optional/None).
    Returns None if resolution fails or TIDAL entity absent.
    Caller responsible for REQUEST_DELAY between calls.
    """
    url = (spotify_url or "").strip()
    if not url:
        return None

    encoded = quote(url, safe="")
    request_url = f"{ODESLI_API}?url={encoded}&platform=spotify"
    try:
        response = httpx.get(request_url, timeout=20.0, follow_redirects=True)
    except Exception as exc:
        logger.info("song.link request failed: %s", exc)
        return None

    if response.status_code == 429:
        logger.info("song.link rate limited (HTTP 429)")
        return None

    if response.status_code != 200:
        logger.info("song.link non-200 response: http_%s", response.status_code)
        return None

    try:
        payload: Any = response.json()
    except Exception as exc:
        logger.info("song.link invalid json: %s", exc)
        return None

    return _extract_ids(payload)


def resolve_isrc_to_tidal(isrc: str) -> dict[str, str | None] | None:
    """
    Resolve an ISRC directly to TIDAL/Qobuz IDs via song.link.
    Uses ?isrc={isrc}&platform=tidal endpoint.
    """
    value = (isrc or "").strip()
    if not value:
        return None

    encoded = quote(value, safe="")
    request_url = f"{ODESLI_API}?isrc={encoded}&platform=tidal"
    try:
        response = httpx.get(request_url, timeout=20.0, follow_redirects=True)
    except Exception as exc:
        logger.info("song.link request failed: %s", exc)
        return None

    if response.status_code == 429:
        logger.info("song.link rate limited (HTTP 429)")
        return None

    if response.status_code != 200:
        logger.info("song.link non-200 response: http_%s", response.status_code)
        return None

    try:
        payload: Any = response.json()
    except Exception as exc:
        logger.info("song.link invalid json: %s", exc)
        return None

    return _extract_ids(payload)

