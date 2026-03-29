from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.enricher import Enricher
from tagslut.metadata.provider_registry import (
    ProviderActivationConfig,
    ProviderPolicy,
    load_provider_activation_config,
    resolve_active_metadata_providers,
    resolve_active_download_providers,
)


def test_registry_defaults_to_beatport_and_tidal() -> None:
    assert resolve_active_metadata_providers() == ["beatport", "tidal"]


def test_unknown_provider_fails_deterministically() -> None:
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_active_metadata_providers(["itunes"])


def test_missing_config_preserves_defaults(tmp_path: Path) -> None:
    cfg = load_provider_activation_config(tmp_path / "missing.toml")
    assert resolve_active_metadata_providers(config=cfg) == ["beatport", "tidal"]


def test_disabled_provider_is_filtered_out(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.tidal]",
                "metadata_enabled = false",
                "download_enabled = false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_provider_activation_config(config_path)

    assert resolve_active_metadata_providers(config=cfg) == ["beatport"]


def test_requested_order_respected_after_filtering() -> None:
    cfg = ProviderActivationConfig(
        beatport=ProviderPolicy(metadata_enabled=False, download_enabled=False),
        tidal=ProviderPolicy(metadata_enabled=True, download_enabled=True),
    )
    assert resolve_active_metadata_providers(["tidal", "beatport"], config=cfg) == ["tidal"]


def test_download_defaults_and_filtering(tmp_path: Path) -> None:
    cfg = load_provider_activation_config(tmp_path / "missing.toml")
    assert resolve_active_download_providers(config=cfg) == ["tidal"]

    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.tidal]",
                "download_enabled = false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    cfg2 = load_provider_activation_config(config_path)
    assert resolve_active_download_providers(config=cfg2) == []


def test_enricher_filters_providers_via_config(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.tidal]",
                "metadata_enabled = false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    token_manager = TokenManager(tokens_path=tmp_path / "tokens.json")
    enricher = Enricher(
        db_path=Path(":memory:"),
        token_manager=token_manager,
        providers=None,
        providers_config_path=config_path,
    )

    assert enricher.provider_names == ["beatport"]
