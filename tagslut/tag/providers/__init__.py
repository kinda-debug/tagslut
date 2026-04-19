from __future__ import annotations

from .base import MetadataProvider, ProviderConfigError

_PROVIDER_REGISTRY: dict[str, MetadataProvider] = {}
_BUILTIN_PROVIDER_ORDER = ("beatport", "tidal", "qobuz")


def _instantiate_builtin_provider(name: str) -> MetadataProvider | None:
    if name == "beatport":
        from .beatport import BeatportTagProvider

        return BeatportTagProvider()
    if name == "tidal":
        from .tidal import TidalTagProvider

        return TidalTagProvider()
    if name == "qobuz":
        from .qobuz import QobuzTagProvider

        return QobuzTagProvider()
    return None


def _ensure_builtin_provider(name: str) -> None:
    if name in _PROVIDER_REGISTRY:
        return
    provider = _instantiate_builtin_provider(name)
    if provider is not None:
        _PROVIDER_REGISTRY[name] = provider


def register_provider(provider: MetadataProvider) -> None:
    _PROVIDER_REGISTRY[provider.name] = provider


def get_provider(name: str) -> MetadataProvider:
    _ensure_builtin_provider(name)
    try:
        return _PROVIDER_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"Unknown metadata provider: {name}") from exc


def clear_provider_registry() -> None:
    _PROVIDER_REGISTRY.clear()


def list_providers() -> list[str]:
    names: list[str] = []
    for name in _BUILTIN_PROVIDER_ORDER:
        if name not in names:
            names.append(name)
    for name in _PROVIDER_REGISTRY:
        if name not in names:
            names.append(name)
    return names


__all__ = [
    "MetadataProvider",
    "ProviderConfigError",
    "clear_provider_registry",
    "get_provider",
    "list_providers",
    "register_provider",
]
