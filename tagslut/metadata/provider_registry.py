"""
Provider registry for metadata providers.

Centralizes provider definitions and activation policy.
"""

from typing import Dict, Type
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


# Default active providers (hard-coded for now)
DEFAULT_ACTIVE_PROVIDERS = ["beatport", "tidal"]
