from __future__ import annotations

from pathlib import Path

import pytest

from tagslut.metadata.provider_registry import (
    get_download_provider_factory,
    load_download_precedence,
    load_provider_activation_config,
    resolve_download_dispatch_order,
)


def test_precedence_default_when_missing_config(tmp_path: Path) -> None:
    precedence = load_download_precedence(tmp_path / "missing.toml")
    assert precedence == ["tidal", "qobuz", "beatport"]


def test_precedence_from_config(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[routing.download]",
                'precedence = ["qobuz", "tidal"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    precedence = load_download_precedence(config_path)
    assert precedence == ["qobuz", "tidal"]


def test_dispatch_order_respects_enabled_and_precedence(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.qobuz]",
                "download_enabled = true",
                "",
                "[providers.tidal]",
                "download_enabled = true",
                "",
                "[routing.download]",
                'precedence = ["qobuz", "tidal", "beatport"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    activation = load_provider_activation_config(config_path)
    precedence = load_download_precedence(config_path)
    order = resolve_download_dispatch_order(activation=activation, precedence=precedence)

    assert order == ["qobuz", "tidal"]


def test_disabled_provider_never_dispatched(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.qobuz]",
                "download_enabled = false",
                "",
                "[routing.download]",
                'precedence = ["qobuz"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    activation = load_provider_activation_config(config_path)
    precedence = load_download_precedence(config_path)
    assert resolve_download_dispatch_order(activation=activation, precedence=precedence) == []


def test_tidal_wrapper_disabled_when_download_enabled_false(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.tidal]",
                "download_enabled = false",
                "",
                "[routing.download]",
                'precedence = ["tidal"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    activation = load_provider_activation_config(config_path)
    precedence = load_download_precedence(config_path)
    assert resolve_download_dispatch_order(activation=activation, precedence=precedence) == []


def test_download_provider_factories_present() -> None:
    assert get_download_provider_factory("tidal").__name__.endswith("DownloadProvider")
    assert get_download_provider_factory("qobuz").__name__.endswith("DownloadProvider")
    assert get_download_provider_factory("beatport").__name__.endswith("DownloadProvider")
