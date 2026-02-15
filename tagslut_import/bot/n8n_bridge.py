"""n8n workflow integration."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class N8NBridge:
    """Send events to an n8n webhook endpoint."""

    def __init__(self, webhook_url: str, *, client: Optional[httpx.AsyncClient] = None) -> None:
        self._webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    async def send_event(self, payload: Dict[str, Any]) -> None:
        """Send ``payload`` to the configured n8n webhook."""

        response = await self._client.post(self._webhook_url, json=payload)
        response.raise_for_status()


__all__ = ["N8NBridge"]
