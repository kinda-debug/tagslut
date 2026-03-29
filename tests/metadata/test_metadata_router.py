from __future__ import annotations

import json
from pathlib import Path

import pytest

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.capabilities import Capability
from tagslut.metadata.enricher import Enricher
from tagslut.metadata.metadata_router import CapabilityUnavailableError, MetadataRouter
from tagslut.metadata.models.types import LocalFileInfo
from tagslut.metadata.provider_registry import ProviderActivationConfig, ProviderPolicy


def _token_manager(tmp_path: Path, tokens: dict) -> TokenManager:
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return TokenManager(tokens_path=tokens_path)


def test_beatport_search_by_text_available_in_degraded_public_mode(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {})
    router = MetadataRouter(
        provider_names=["beatport"],
        activation=ProviderActivationConfig(),
        token_manager=tm,
    )

    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT) == ["beatport"]


def test_beatport_search_by_isrc_unavailable_without_auth(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {})
    router = MetadataRouter(
        provider_names=["beatport"],
        activation=ProviderActivationConfig(),
        token_manager=tm,
    )

    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_ISRC) == []


def test_tidal_export_playlist_seed_unavailable_without_auth(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {})
    router = MetadataRouter(
        provider_names=["tidal"],
        activation=ProviderActivationConfig(),
        token_manager=tm,
    )

    assert router.provider_names_for(Capability.METADATA_EXPORT_PLAYLIST_SEED) == []


def test_router_picks_first_enabled_provider_with_capability(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {})
    router = MetadataRouter(
        provider_names=["tidal", "beatport"],
        activation=ProviderActivationConfig(),
        token_manager=tm,
    )

    assert router.first_provider_name_for(Capability.METADATA_SEARCH_BY_TEXT) == "beatport"


def test_router_skips_disabled_provider(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {"tidal": {"refresh_token": "r1"}})
    activation = ProviderActivationConfig(tidal=ProviderPolicy(metadata_enabled=False))
    router = MetadataRouter(
        provider_names=["tidal", "beatport"],
        activation=activation,
        token_manager=tm,
    )

    assert router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT) == ["beatport"]


def test_deterministic_failure_when_no_provider_can_satisfy_capability(tmp_path: Path) -> None:
    tm = _token_manager(tmp_path, {})
    router = MetadataRouter(
        provider_names=["beatport"],
        activation=ProviderActivationConfig(),
        token_manager=tm,
    )

    with pytest.raises(CapabilityUnavailableError):
        router.first_provider_name_for(Capability.METADATA_SEARCH_BY_ISRC)


def test_isrc_resolution_failure_sets_uncertain_ingestion_confidence(tmp_path: Path) -> None:
    token_manager = _token_manager(tmp_path, {})
    enricher = Enricher(
        db_path=Path(":memory:"),
        token_manager=token_manager,
        providers=["beatport"],
        dry_run=True,
        mode="recovery",
    )
    file_info = LocalFileInfo(path="x.flac", tag_isrc="USRC17607839")

    result = enricher.resolve_file(file_info)

    assert result.ingestion_confidence == "uncertain"
