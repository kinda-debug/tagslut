from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from tagslut.intake.songlink import resolve_spotify_to_tidal


class IntakeError(RuntimeError):
    pass


@dataclass(frozen=True)
class IntakeDispatch:
    url: str
    spotify_url: str | None = None


_SPOTIFY_KIND_RE = re.compile(r"^/(?:intl-[a-z]{2}/)?(track|album|playlist)/", re.IGNORECASE)


def _spotify_kind(url: str) -> str | None:
    parsed = urlparse((url or "").strip())
    host = (parsed.netloc or "").lower()
    if host != "open.spotify.com":
        return None
    match = _SPOTIFY_KIND_RE.match(parsed.path or "")
    if not match:
        return None
    return match.group(1).lower()


def dispatch_intake_url(url: str) -> IntakeDispatch:
    """
    Normalize intake URLs for the downloader pipeline.

    - Spotify track URLs are resolved to TIDAL track URLs via song.link.
    - Spotify album / playlist URLs raise IntakeError (not yet supported).
    """
    raw = (url or "").strip()
    kind = _spotify_kind(raw)
    if kind is None:
        return IntakeDispatch(url=raw, spotify_url=None)

    if kind in {"album", "playlist"}:
        raise IntakeError("Spotify album/playlist URLs are not supported yet")

    resolved = resolve_spotify_to_tidal(raw)
    tidal_id = (resolved or {}).get("tidal_id")
    if not tidal_id:
        raise IntakeError("song.link could not resolve this Spotify URL to a TIDAL track")

    return IntakeDispatch(url=f"https://tidal.com/track/{tidal_id}", spotify_url=raw)

