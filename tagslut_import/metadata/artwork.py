"""Artwork downloading utilities."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from tagslut.core.models import Artwork
from tagslut.core.paths import PathManager


@dataclass(slots=True)
class ArtworkDownload:
    """Represents a downloaded artwork asset."""

    artwork: Artwork
    path: Path


class ArtworkFetcher:
    """Download and cache artwork assets referenced in metadata."""

    def __init__(
        self,
        path_manager: PathManager,
        *,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._path_manager = path_manager
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    async def download(
        self,
        artwork: Artwork,
        *,
        filename: Optional[str] = None,
        force: bool = False,
    ) -> ArtworkDownload:
        """Download the provided :class:`Artwork` and return the cached path."""

        target_name = filename or self._generate_filename(artwork)
        destination = self._path_manager.cache_path("artwork", target_name)
        if destination.exists() and not force:
            return ArtworkDownload(artwork=artwork, path=destination)

        response = await self._client.get(str(artwork.url))
        response.raise_for_status()
        destination.write_bytes(response.content)
        return ArtworkDownload(artwork=artwork, path=destination)

    def _generate_filename(self, artwork: Artwork) -> str:
        """Generate a deterministic filename for the artwork asset."""

        digest = hashlib.sha256(str(artwork.url).encode("utf-8")).hexdigest()
        extension = _guess_extension(artwork.mime_type)
        return f"{digest}{extension}"


def _guess_extension(mime_type: Optional[str]) -> str:
    if not mime_type:
        return ".bin"
    if "png" in mime_type:
        return ".png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        return ".jpg"
    if "gif" in mime_type:
        return ".gif"
    return ".bin"


__all__ = ["ArtworkDownload", "ArtworkFetcher"]
