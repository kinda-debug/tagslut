from __future__ import annotations

import json
from pathlib import Path

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.capabilities import Capability
from tagslut.metadata.metadata_router import MetadataRouter
from tagslut.metadata.provider_registry import (
    ProviderActivationConfig,
    ProviderPolicy,
    get_provider_class,
    resolve_active_metadata_providers,
)


def _token_manager(tmp_path: Path) -> TokenManager:
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(json.dumps({}, indent=2), encoding="utf-8")
    return TokenManager(tokens_path=tokens_path)


def test_qobuz_registry_present_but_disabled_by_default(tmp_path: Path) -> None:
    assert get_provider_class("qobuz").name == "qobuz"
    assert "qobuz" not in resolve_active_metadata_providers(config=ProviderActivationConfig())


def test_qobuz_does_not_route_when_disabled(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path)
    activation = ProviderActivationConfig()
    router = MetadataRouter(provider_names=["qobuz"], activation=activation, token_manager=tm)

    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT) == []


def test_enabling_qobuz_exposes_metadata_capabilities(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path)
    activation = ProviderActivationConfig(
        qobuz=ProviderPolicy(
            metadata_enabled=True,
            download_enabled=False,
            trust="do_not_use_for_canonical",
        )
    )
    router = MetadataRouter(provider_names=["qobuz"], activation=activation, token_manager=tm)

    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT) == ["qobuz"]
    assert router.provider_names_for(Capability.METADATA_FETCH_TRACK_BY_ID) == ["qobuz"]
    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_ISRC) == ["qobuz"]
