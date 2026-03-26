"""Helpers for constructing and caching the generated tagslut API SDK client.

This module intentionally keeps integration minimal:
- Read configuration from environment variables once.
- Build a configured SDK client.
- Expose a cached get_client() entrypoint for reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from typing import Any


@dataclass(frozen=True)
class TagslutApiClientConfig:
    """Runtime configuration for the generated tagslut API SDK client."""

    base_url: str
    access_token: str | None = None
    username: str | None = None
    password: str | None = None
    timeout_ms: int = 10_000


def _read_timeout_ms() -> int:
    raw_timeout = os.getenv("TAGSLUT_API_TIMEOUT_MS") or os.getenv("timeout_ms")
    if not raw_timeout:
        return 10_000
    try:
        timeout = int(raw_timeout)
    except ValueError as exc:
        raise ValueError(
            "TAGSLUT_API_TIMEOUT_MS must be an integer number of milliseconds"
        ) from exc
    if timeout <= 0:
        raise ValueError("TAGSLUT_API_TIMEOUT_MS must be greater than 0")
    return timeout


def load_config_from_env() -> TagslutApiClientConfig:
    """Load SDK client configuration from environment variables."""

    base_url = os.getenv("TAGSLUT_API_BASE_URL") or os.getenv("base_url")
    if not base_url:
        raise ValueError(
            "Missing API base URL. Set TAGSLUT_API_BASE_URL (or base_url)."
        )

    return TagslutApiClientConfig(
        base_url=base_url,
        access_token=os.getenv("TAGSLUT_API_ACCESS_TOKEN") or os.getenv("access_token"),
        username=os.getenv("TAGSLUT_API_USERNAME") or os.getenv("username"),
        password=os.getenv("TAGSLUT_API_PASSWORD") or os.getenv("password"),
        timeout_ms=_read_timeout_ms(),
    )


def build_client(config: TagslutApiClientConfig) -> Any:
    """Build a TagslutApiSdk client from a resolved config object."""

    try:
        from tagslut_api_sdk import TagslutApiSdk
    except ImportError as exc:
        raise ImportError(
            "tagslut_api_sdk is not available. Install dependencies with poetry install."
        ) from exc

    return TagslutApiSdk(
        access_token=config.access_token,
        username=config.username,
        password=config.password,
        base_url=config.base_url,
        timeout=config.timeout_ms,
    )


@lru_cache(maxsize=1)
def get_client() -> Any:
    """Return a cached TagslutApiSdk instance configured from environment."""

    return build_client(load_config_from_env())


def reset_client_cache() -> None:
    """Clear the cached SDK instance so env changes can be applied."""

    get_client.cache_clear()
