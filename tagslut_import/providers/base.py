"""Base classes and helpers for provider integrations."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import httpx

from tagslut.core.models import Album, ProviderInfo, Track


class ProviderError(RuntimeError):
    """Raised when a provider returns an error response."""


@dataclass(slots=True)
class ProviderCredentials:
    """Container for provider authentication credentials."""

    token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


@dataclass(slots=True)
class ProviderContext:
    """Runtime context for provider calls."""

    credentials: ProviderCredentials
    client: httpx.AsyncClient


class MusicProvider(abc.ABC):
    """Abstract base class for music metadata providers."""

    name: str

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    @abc.abstractmethod
    async def search_track(self, query: str, *, limit: int = 5) -> List[Track]:
        """Search for tracks matching the provided query."""

    @abc.abstractmethod
    async def get_track(self, external_id: str) -> Track:
        """Fetch a single track by its provider-specific identifier."""

    @abc.abstractmethod
    async def get_album(self, external_id: str) -> Album:
        """Fetch album metadata by its provider-specific identifier."""

    async def _request(self, method: str, url: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute a request and return parsed JSON."""

        response = await self._client.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(
                f"{self.name} responded with status {response.status_code}: {response.text}"
            )
        return response.json()

    def _make_provider_info(
        self, *, external_id: Optional[str] = None, url: Optional[str] = None
    ) -> ProviderInfo:
        """Create a :class:`ProviderInfo` instance for the provider."""

        return ProviderInfo(name=self.name, external_id=external_id, url=url)

    @staticmethod
    def _truncate_results(items: Iterable[Track], limit: int) -> List[Track]:
        """Return up to ``limit`` items from ``items``."""

        results = list(items)
        return results[:limit]


__all__ = [
    "MusicProvider",
    "ProviderContext",
    "ProviderCredentials",
    "ProviderError",
]
