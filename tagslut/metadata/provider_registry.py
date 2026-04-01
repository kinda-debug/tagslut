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
from tagslut.metadata.providers.qobuz import QobuzProvider
from tagslut.metadata.providers.reccobeats import ReccoBeatsProvider
from tagslut.metadata.providers.tidal import TidalProvider

# Registry of available providers
PROVIDER_REGISTRY: Dict[str, Type[AbstractProvider]] = {
    "beatport": BeatportProvider,
    "tidal": TidalProvider,
    "qobuz": QobuzProvider,
    "reccobeats": ReccoBeatsProvider,
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
    qobuz: ProviderPolicy = ProviderPolicy(
        metadata_enabled=False,
        download_enabled=False,
        trust="do_not_use_for_canonical",
    )
    reccobeats: ProviderPolicy = ProviderPolicy(
        metadata_enabled=True,
        download_enabled=False,
        trust="secondary",
    )


DEFAULT_ACTIVE_PROVIDERS = ["beatport", "tidal", "qobuz", "reccobeats"]
DEFAULT_DOWNLOAD_PRECEDENCE = ["tidal", "qobuz", "beatport"]
DEFAULT_PROVIDERS_CONFIG_PATH = (
    Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "tagslut"
    / "providers.toml"
)


def _parse_trust(raw: object, *, provider: str, default: ProviderTrust) -> ProviderTrust:
    if raw is None:
        return default
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
    qobuz_section = providers.get("qobuz") if isinstance(providers.get("qobuz"), dict) else {}
    reccobeats_section = providers.get("reccobeats") if isinstance(providers.get("reccobeats"), dict) else {}

    beatport_policy = ProviderPolicy(
        metadata_enabled=bool(beatport_section.get("metadata_enabled", True)),
        download_enabled=bool(beatport_section.get("download_enabled", False)),
        trust=_parse_trust(beatport_section.get("trust"), provider="beatport", default="dj_primary"),
    )
    tidal_policy = ProviderPolicy(
        metadata_enabled=bool(tidal_section.get("metadata_enabled", True)),
        download_enabled=bool(tidal_section.get("download_enabled", True)),
        trust=_parse_trust(tidal_section.get("trust"), provider="tidal", default="dj_primary"),
    )
    qobuz_policy = ProviderPolicy(
        metadata_enabled=bool(qobuz_section.get("metadata_enabled", False)),
        download_enabled=bool(qobuz_section.get("download_enabled", False)),
        trust=_parse_trust(qobuz_section.get("trust"), provider="qobuz", default="do_not_use_for_canonical"),
    )

    reccobeats_policy = ProviderPolicy(
        metadata_enabled=bool(reccobeats_section.get("metadata_enabled", True)),
        download_enabled=bool(reccobeats_section.get("download_enabled", False)),
        trust=_parse_trust(reccobeats_section.get("trust"), provider="reccobeats", default="secondary"),
    )

    return ProviderActivationConfig(
        beatport=beatport_policy,
        tidal=tidal_policy,
        qobuz=qobuz_policy,
        reccobeats=reccobeats_policy,
    )


def load_download_precedence(path: Path | None = None) -> list[str]:
    """
    Load download routing precedence from providers.toml.

    Optional config:
      [routing.download]
      precedence = ["tidal", "qobuz", "beatport"]
    """
    config_path = path or DEFAULT_PROVIDERS_CONFIG_PATH
    config_path = Path(os.path.expanduser(str(config_path)))
    if not config_path.exists():
        return list(DEFAULT_DOWNLOAD_PRECEDENCE)

    import tomllib

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    routing = data.get("routing") if isinstance(data, dict) else None
    routing = routing if isinstance(routing, dict) else {}
    download = routing.get("download") if isinstance(routing.get("download"), dict) else {}
    precedence = download.get("precedence") if isinstance(download, dict) else None

    if precedence is None:
        return list(DEFAULT_DOWNLOAD_PRECEDENCE)
    if isinstance(precedence, str):
        parts = [p.strip() for p in precedence.split(",") if p.strip()]
        return parts or list(DEFAULT_DOWNLOAD_PRECEDENCE)
    if isinstance(precedence, list):
        parts = [str(p).strip() for p in precedence if str(p).strip()]
        return parts or list(DEFAULT_DOWNLOAD_PRECEDENCE)
    return list(DEFAULT_DOWNLOAD_PRECEDENCE)


def get_download_provider_factory(provider: str):
    from tagslut.download.providers import (
        BeatportStoreDownloadProvider,
        QobuzPurchaseDownloadProvider,
        TidalWrapperDownloadProvider,
    )

    if provider == "tidal":
        return TidalWrapperDownloadProvider
    if provider == "qobuz":
        return QobuzPurchaseDownloadProvider
    if provider == "beatport":
        return BeatportStoreDownloadProvider
    raise ValueError(f"Unknown download provider: {provider}")


def resolve_download_dispatch_order(
    *,
    activation: ProviderActivationConfig,
    precedence: list[str],
) -> list[str]:
    ordered: list[str] = []
    for name in precedence:
        if name == "tidal" and activation.tidal.download_enabled:
            ordered.append("tidal")
        elif name == "qobuz" and activation.qobuz.download_enabled:
            ordered.append("qobuz")
        elif name == "beatport" and activation.beatport.download_enabled:
            ordered.append("beatport")
        else:
            continue
    return ordered


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
    if cfg.qobuz.metadata_enabled:
        enabled.add("qobuz")
    if cfg.reccobeats.metadata_enabled:
        enabled.add("reccobeats")

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
