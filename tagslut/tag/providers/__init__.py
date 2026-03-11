from __future__ import annotations

from .base import MetadataProvider

_PROVIDER_REGISTRY: dict[str, MetadataProvider] = {}


def register_provider(provider: MetadataProvider) -> None:
    _PROVIDER_REGISTRY[provider.name] = provider


def get_provider(name: str) -> MetadataProvider:
    try:
        return _PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown metadata provider: {name}") from exc


def clear_provider_registry() -> None:
    _PROVIDER_REGISTRY.clear()


def list_providers() -> list[str]:
    return sorted(_PROVIDER_REGISTRY.keys())


__all__ = [
    "MetadataProvider",
    "clear_provider_registry",
    "get_provider",
    "list_providers",
    "register_provider",
]
