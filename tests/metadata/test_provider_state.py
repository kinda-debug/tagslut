from __future__ import annotations

import json
import time
from pathlib import Path

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.provider_registry import (
    ProviderActivationConfig,
    ProviderPolicy,
)
from tagslut.metadata.provider_state import ProviderState, resolve_provider_status


def _tm(tmp_path: Path, tokens: dict) -> TokenManager:
    tokens_path = tmp_path / "tokens.json"
    if tokens is not None:
        tokens_path.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    return TokenManager(tokens_path=tokens_path)


def test_beatport_enabled_degraded_public_only_when_no_token(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("beatport", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_degraded_public_only
    assert status.metadata_usable is True


def test_beatport_disabled_by_policy(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {"beatport": {"access_token": "a1"}})
    activation = ProviderActivationConfig(beatport=ProviderPolicy(metadata_enabled=False))
    status = resolve_provider_status("beatport", activation=activation, token_manager=tm)

    assert status.state == ProviderState.disabled
    assert status.metadata_usable is False


def test_tidal_unconfigured_when_no_tokens(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_unconfigured
    assert status.metadata_usable is False


def test_tidal_configured_unauthenticated_when_refresh_only(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {"tidal": {"refresh_token": "r1"}})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_configured_unauthenticated
    assert status.metadata_usable is True


def test_tidal_authenticated_when_access_token_valid(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {"tidal": {"access_token": "a1", "expires_at": time.time() + 10_000}})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_authenticated
    assert status.metadata_usable is True


def test_tidal_expired_refreshable_when_access_expired_and_refresh_present(tmp_path: Path) -> None:
    tm = _tm(
        tmp_path,
        {"tidal": {"access_token": "a1", "refresh_token": "r1", "expires_at": time.time() - 10_000}},
    )
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_expired_refreshable
    assert status.metadata_usable is True


def test_tidal_expired_unrefreshable_when_access_expired_and_no_refresh(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {"tidal": {"access_token": "a1", "expires_at": time.time() - 10_000}})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state == ProviderState.enabled_expired_unrefreshable
    assert status.metadata_usable is False


def test_subscription_inactive_is_not_emitted_without_probe(tmp_path: Path) -> None:
    tm = _tm(tmp_path, {"tidal": {"access_token": "a1", "expires_at": time.time() + 10_000}})
    activation = ProviderActivationConfig()
    status = resolve_provider_status("tidal", activation=activation, token_manager=tm)

    assert status.state != ProviderState.enabled_subscription_inactive

