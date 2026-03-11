from __future__ import annotations

from .base import MetadataProvider, ProviderConfigError

_PROVIDER_REGISTRY: dict[str, MetadataProvider] = {}


def _builtin_factories() -> dict[str, type[MetadataProvider]]:
    from .spotify import SpotifyProvider

    return {"spotify": SpotifyProvider}


def _ensure_builtin(name: str | None = None) -> None:
    factories = _builtin_factories()
    if name is None:
        for provider_name, factory in factories.items():
            if provider_name not in _PROVIDER_REGISTRY:
                _PROVIDER_REGISTRY[provider_name] = factory()
        return

    if name in factories and name not in _PROVIDER_REGISTRY:
        _PROVIDER_REGISTRY[name] = factories[name]()


def register_provider(provider: MetadataProvider) -> None:
    _PROVIDER_REGISTRY[provider.name] = provider


def get_provider(name: str) -> MetadataProvider:
    _ensure_builtin(name)
    try:
        return _PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown metadata provider: {name}") from exc


def clear_provider_registry() -> None:
    _PROVIDER_REGISTRY.clear()


def list_providers() -> list[str]:
    _ensure_builtin()
    return sorted(_PROVIDER_REGISTRY.keys())


__all__ = [
    "MetadataProvider",
    "ProviderConfigError",
    "clear_provider_registry",
    "get_provider",
    "list_providers",
    "register_provider",
]
