"""
Provider state resolution for metadata providers.

Note on contract drift:
- docs/contracts/provider_matching.md describes TIDAL auth as OAuth Authorization Code + PKCE with
  a separate token store.
- The current runtime TokenManager (tagslut/metadata/auth.py) uses a device-style flow and stores
  tokens in ~/.config/tagslut/tokens.json (and may bridge from tiddl config).

This module reflects the *actual* TokenManager behavior, not the contract's aspirational auth model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from tagslut.metadata.auth import TokenManager, TokenInfo
from tagslut.metadata.provider_registry import ProviderActivationConfig, ProviderTrust


class ProviderState(str, Enum):
    disabled = "disabled"
    enabled_unconfigured = "enabled_unconfigured"
    enabled_configured_unauthenticated = "enabled_configured_unauthenticated"
    enabled_authenticated = "enabled_authenticated"
    enabled_expired_refreshable = "enabled_expired_refreshable"
    enabled_expired_unrefreshable = "enabled_expired_unrefreshable"
    enabled_degraded_public_only = "enabled_degraded_public_only"
    enabled_subscription_inactive = "enabled_subscription_inactive"


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    metadata_enabled: bool
    trust: ProviderTrust
    state: ProviderState
    has_access_token: bool
    has_refresh_token: bool
    is_expired: Optional[bool]
    metadata_usable: bool


@dataclass(frozen=True)
class DownloadProviderStatus:
    provider: str
    download_enabled: bool
    trust: ProviderTrust
    state: ProviderState
    has_access_token: bool
    has_refresh_token: bool
    is_expired: Optional[bool]
    download_usable: bool


def _get_raw_provider_data(token_manager: TokenManager, provider: str) -> dict[str, Any]:
    data = getattr(token_manager, "_tokens", {}).get(provider, {})
    return data if isinstance(data, dict) else {}


def _get_token(token_manager: TokenManager, provider: str) -> Optional[TokenInfo]:
    try:
        return token_manager.get_token(provider)
    except Exception:
        return None


def resolve_provider_status(
    provider: str,
    *,
    activation: ProviderActivationConfig,
    token_manager: TokenManager,
) -> ProviderStatus:
    if provider == "beatport":
        policy = activation.beatport
    elif provider == "tidal":
        policy = activation.tidal
    elif provider == "qobuz":
        policy = activation.qobuz
    elif provider == "reccobeats":
        policy = activation.reccobeats
    else:
        raise ValueError(f"Unknown provider: {provider}")

    if not policy.metadata_enabled:
        return ProviderStatus(
            provider=provider,
            metadata_enabled=False,
            trust=policy.trust,
            state=ProviderState.disabled,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            metadata_usable=False,
        )

    raw = _get_raw_provider_data(token_manager, provider)
    has_refresh = bool(raw.get("refresh_token"))

    token = _get_token(token_manager, provider)
    has_access = bool(token and token.access_token)
    is_expired = token.is_expired if token else None

    if provider == "beatport":
        if not has_access:
            return ProviderStatus(
                provider=provider,
                metadata_enabled=True,
                trust=policy.trust,
                state=ProviderState.enabled_degraded_public_only,
                has_access_token=False,
                has_refresh_token=has_refresh,
                is_expired=None,
                metadata_usable=True,
            )

        if is_expired:
            state = ProviderState.enabled_expired_refreshable if has_refresh else ProviderState.enabled_degraded_public_only
            return ProviderStatus(
                provider=provider,
                metadata_enabled=True,
                trust=policy.trust,
                state=state,
                has_access_token=True,
                has_refresh_token=has_refresh,
                is_expired=True,
                metadata_usable=True,
            )

        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_authenticated,
            has_access_token=True,
            has_refresh_token=has_refresh,
            is_expired=False,
            metadata_usable=True,
        )

    if provider == "qobuz":
        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_authenticated,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            metadata_usable=True,
        )

    if provider == "reccobeats":
        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_authenticated,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            metadata_usable=True,
        )

    # tidal
    if has_access:
        if is_expired:
            state = ProviderState.enabled_expired_refreshable if has_refresh else ProviderState.enabled_expired_unrefreshable
            usable = state == ProviderState.enabled_expired_refreshable
            return ProviderStatus(
                provider=provider,
                metadata_enabled=True,
                trust=policy.trust,
                state=state,
                has_access_token=True,
                has_refresh_token=has_refresh,
                is_expired=True,
                metadata_usable=usable,
            )
        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_authenticated,
            has_access_token=True,
            has_refresh_token=has_refresh,
            is_expired=False,
            metadata_usable=True,
        )

    if has_refresh:
        return ProviderStatus(
            provider=provider,
            metadata_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_configured_unauthenticated,
            has_access_token=False,
            has_refresh_token=True,
            is_expired=None,
            metadata_usable=True,
        )

    return ProviderStatus(
        provider=provider,
        metadata_enabled=True,
        trust=policy.trust,
        state=ProviderState.enabled_unconfigured,
        has_access_token=False,
        has_refresh_token=False,
        is_expired=None,
        metadata_usable=False,
    )


def resolve_metadata_provider_statuses(
    *,
    activation: ProviderActivationConfig,
    token_manager: TokenManager,
) -> dict[str, ProviderStatus]:
    return {
        "beatport": resolve_provider_status("beatport", activation=activation, token_manager=token_manager),
        "tidal": resolve_provider_status("tidal", activation=activation, token_manager=token_manager),
        "qobuz": resolve_provider_status("qobuz", activation=activation, token_manager=token_manager),
        "reccobeats": resolve_provider_status("reccobeats", activation=activation, token_manager=token_manager),
    }


def resolve_download_provider_status(
    provider: str,
    *,
    activation: ProviderActivationConfig,
    token_manager: TokenManager,
) -> DownloadProviderStatus:
    if provider == "beatport":
        policy = activation.beatport
    elif provider == "tidal":
        policy = activation.tidal
    elif provider == "qobuz":
        policy = activation.qobuz
    elif provider == "reccobeats":
        policy = activation.reccobeats
    else:
        raise ValueError(f"Unknown provider: {provider}")

    if not policy.download_enabled:
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=False,
            trust=policy.trust,
            state=ProviderState.disabled,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            download_usable=False,
        )

    raw = _get_raw_provider_data(token_manager, provider)
    has_refresh = bool(raw.get("refresh_token"))

    token = _get_token(token_manager, provider)
    has_access = bool(token and token.access_token)
    is_expired = token.is_expired if token else None

    if provider == "beatport":
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_unconfigured,
            has_access_token=has_access,
            has_refresh_token=has_refresh,
            is_expired=is_expired,
            download_usable=True,
        )

    if provider == "qobuz":
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_unconfigured,
            has_access_token=has_access,
            has_refresh_token=has_refresh,
            is_expired=is_expired,
            download_usable=False,
        )

    if provider == "reccobeats":
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_unconfigured,
            has_access_token=False,
            has_refresh_token=False,
            is_expired=None,
            download_usable=False,
        )

    # tidal download is auth-gated
    if has_access and not is_expired:
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_authenticated,
            has_access_token=True,
            has_refresh_token=has_refresh,
            is_expired=False,
            download_usable=True,
        )

    if (has_access and is_expired) and has_refresh:
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_expired_refreshable,
            has_access_token=True,
            has_refresh_token=True,
            is_expired=True,
            download_usable=True,
        )

    if has_refresh:
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_configured_unauthenticated,
            has_access_token=False,
            has_refresh_token=True,
            is_expired=None,
            download_usable=True,
        )

    if has_access and is_expired:
        return DownloadProviderStatus(
            provider=provider,
            download_enabled=True,
            trust=policy.trust,
            state=ProviderState.enabled_expired_unrefreshable,
            has_access_token=True,
            has_refresh_token=False,
            is_expired=True,
            download_usable=False,
        )

    return DownloadProviderStatus(
        provider=provider,
        download_enabled=True,
        trust=policy.trust,
        state=ProviderState.enabled_unconfigured,
        has_access_token=False,
        has_refresh_token=False,
        is_expired=None,
        download_usable=False,
    )


def resolve_download_provider_statuses(
    *,
    activation: ProviderActivationConfig,
    token_manager: TokenManager,
) -> dict[str, DownloadProviderStatus]:
    return {
        "beatport": resolve_download_provider_status("beatport", activation=activation, token_manager=token_manager),
        "tidal": resolve_download_provider_status("tidal", activation=activation, token_manager=token_manager),
        "qobuz": resolve_download_provider_status("qobuz", activation=activation, token_manager=token_manager),
        "reccobeats": resolve_download_provider_status("reccobeats", activation=activation, token_manager=token_manager),
    }


def format_provider_status_lines(
    metadata_statuses: dict[str, ProviderStatus],
    download_statuses: dict[str, DownloadProviderStatus],
) -> list[str]:
    lines: list[str] = []
    for name in ("beatport", "tidal", "qobuz", "reccobeats"):
        s = metadata_statuses[name]
        d = download_statuses[name]
        lines.append(
            " ".join(
                [
                    f"{s.provider}",
                    f"metadata_state={s.state.value}",
                    f"metadata_enabled={str(s.metadata_enabled).lower()}",
                    f"download_state={d.state.value}",
                    f"download_enabled={str(d.download_enabled).lower()}",
                    f"trust={s.trust}",
                    f"access={'yes' if s.has_access_token else 'no'}",
                    f"refresh={'yes' if s.has_refresh_token else 'no'}",
                    f"metadata_usable={'yes' if s.metadata_usable else 'no'}",
                    f"download_usable={'yes' if d.download_usable else 'no'}",
                ]
            )
        )
    return lines
