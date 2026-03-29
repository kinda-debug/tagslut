"""
Provider registry for metadata providers.

Centralizes provider definitions plus optional activation policy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Literal, Type

from tagslut.metadata.providers.base import AbstractProvider
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.tidal import TidalProvider

# Registry of available providers
PROVIDER_REGISTRY: Dict[str, Type[AbstractProvider]] = {
    "beatport": BeatportProvider,
    "tidal": TidalProvider,
}


def get_provider_class(name: str) -> Type[AbstractProvider]:
    if name not in PROVIDER_REGISTRY:
        raise ValueError(f"Unknown provider: {name}")
    return PROVIDER_REGISTRY[name]


ProviderTrust = Literal["dj_primary", "secondary", "do_not_use_for_canonical"]


@dataclass(frozen=True)
class ProviderPolicy:
    metadata_enabled: bool = True
    download_enabled: bool = False
    # Default trust for authoritative providers (beatport, tidal) is "dj_primary".
    # Use "secondary" or "do_not_use_for_canonical" explicitly in providers.toml for
    # non-authoritative providers (e.g. qobuz before corroboration is established).
    trust: ProviderTrust = "dj_primary"


@dataclass(frozen=True)
class ProviderActivationConfig:
    beatport: ProviderPolicy = ProviderPolicy(download_enabled=False)
    tidal: ProviderPolicy = ProviderPolicy(download_enabled=True)


DEFAULT_ACTIVE_PROVIDERS = ["beatport", "tidal"]
DEFAULT_PROVIDERS_CONFIG_PATH = (
    Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "tagslut"
    / "providers.toml"
)


def _parse_trust(raw: object, *, provider: str) -> ProviderTrust:
    if raw is None:
        return "secondary"
    if isinstance(raw, str) and raw in ("dj_primary", "secondary", "do_not_use_for_canonical"):
        return raw  # type: ignore[return-value]  # Literal narrowing
    raise ValueError(f"Invalid trust for {provider}: {raw!r}")


def load_provider_activation_config(path: Path | None = None) -> ProviderActivationConfig:
    """
    Load provider activation policy from a TOML config file.

    File is optional: if missing, defaults preserve current behavior (Beatport + TIDAL enabled).
    """
    config_path = path or DEFAULT_PROVIDERS_CONFIG_PATH
    config_path = Path(os.path.expanduser(str(config_path)))
    if not config_path.exists():
        return ProviderActivationConfig()

    import tomllib

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    providers = data.get("providers") if isinstance(data, dict) else None
    providers = providers if isinstance(providers, dict) else {}

    beatport_section = providers.get("beatport") if isinstance(providers.get("beatport"), dict) else {}
    tidal_section = providers.get("tidal") if isinstance(providers.get("tidal"), dict) else {}

    beatport_policy = ProviderPolicy(
        metadata_enabled=bool(beatport_section.get("metadata_enabled", True)),
        download_enabled=bool(beatport_section.get("download_enabled", False)),
        trust=_parse_trust(beatport_section.get("trust"), provider="beatport"),
    )
    tidal_policy = ProviderPolicy(
        metadata_enabled=bool(tidal_section.get("metadata_enabled", True)),
        download_enabled=bool(tidal_section.get("download_enabled", True)),
        trust=_parse_trust(tidal_section.get("trust"), provider="tidal"),
    )

    return ProviderActivationConfig(beatport=beatport_policy, tidal=tidal_policy)


def resolve_active_metadata_providers(
    requested: list[str] | None = None,
    *,
    config: ProviderActivationConfig | None = None,
) -> list[str]:
    """
    Resolve the ordered list of metadata providers to use.

    - Unknown providers raise ValueError deterministically.
    - If config is absent, defaults preserve current behavior (Beatport + TIDAL enabled).
    - If config is present, providers disabled via metadata_enabled are filtered out.
    - Order is preserved across enabled providers.
    """
    base = requested or list(DEFAULT_ACTIVE_PROVIDERS)

    for name in base:
        get_provider_class(name)

    cfg = config or ProviderActivationConfig()
    enabled: set[str] = set()
    if cfg.beatport.metadata_enabled:
        enabled.add("beatport")
    if cfg.tidal.metadata_enabled:
        enabled.add("tidal")

    return [name for name in base if name in enabled]


def resolve_active_download_providers(
    requested: list[str] | None = None,
    *,
    config: ProviderActivationConfig | None = None,
) -> list[str]:
    """
    Resolve the ordered list of download providers to use.

    This is policy-only scaffolding for now (no download routing is implemented here).
    """
    base = requested or list(DEFAULT_ACTIVE_PROVIDERS)

    for name in base:
        get_provider_class(name)

    cfg = config or ProviderActivationConfig()
    enabled: set[str] = set()
    if cfg.beatport.download_enabled:
        enabled.add("beatport")
    if cfg.tidal.download_enabled:
        enabled.add("tidal")

    return [name for name in base if name in enabled]
