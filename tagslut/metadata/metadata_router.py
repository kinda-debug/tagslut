"""Capability-aware metadata provider routing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from tagslut.metadata.capabilities import Capability
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.provider_registry import (
    ProviderActivationConfig,
    get_provider_class,
)
from tagslut.metadata.provider_state import ProviderState, resolve_provider_status


class ISRCResolutionFallbackPolicy(str, Enum):
    PROCEED_UNCERTAIN = "proceed_uncertain"


DEFAULT_ISRC_FALLBACK_POLICY = ISRCResolutionFallbackPolicy.PROCEED_UNCERTAIN


class CapabilityUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityDecision:
    provider: str
    allowed: bool
    reason: str


def _supports_capability(provider: str, capability: Capability) -> bool:
    provider_cls = get_provider_class(provider)
    supported = getattr(provider_cls, "capabilities", None)
    return bool(supported and capability in supported)


def _capability_available_for_state(
    *,
    provider: str,
    capability: Capability,
    state: ProviderState,
    has_access_token: bool,
    has_refresh_token: bool,
    metadata_usable: bool,
) -> tuple[bool, str]:
    if state == ProviderState.disabled:
        return False, "disabled by policy"

    # Capabilities that imply we can make metadata calls at all.
    if capability in (
        Capability.METADATA_FETCH_TRACK_BY_ID,
        Capability.METADATA_SEARCH_BY_ISRC,
        Capability.METADATA_SEARCH_BY_TEXT,
        Capability.METADATA_EXPORT_PLAYLIST_SEED,
        Capability.METADATA_FETCH_ARTWORK,
    ):
        if not metadata_usable and capability != Capability.METADATA_SEARCH_BY_TEXT:
            return False, f"state={state.value}"

    if provider == "beatport":
        if capability == Capability.METADATA_SEARCH_BY_TEXT:
            # Beatport has public fallbacks (web scraping / Next.js data endpoints).
            return True, f"state={state.value}"
        if capability == Capability.METADATA_SEARCH_BY_ISRC:
            if not has_access_token:
                return False, "requires catalog auth (no access token)"
            if state == ProviderState.enabled_degraded_public_only:
                return False, "degraded public-only"
            return True, f"state={state.value}"
        if capability == Capability.METADATA_EXPORT_PLAYLIST_SEED:
            return False, "not supported by provider"
        if capability == Capability.METADATA_FETCH_TRACK_BY_ID:
            return True, f"state={state.value}"
        if capability == Capability.METADATA_FETCH_ARTWORK:
            return True, f"state={state.value}"

    if provider == "tidal":
        if capability in (
            Capability.METADATA_FETCH_TRACK_BY_ID,
            Capability.METADATA_SEARCH_BY_TEXT,
            Capability.METADATA_SEARCH_BY_ISRC,
            Capability.METADATA_EXPORT_PLAYLIST_SEED,
            Capability.METADATA_FETCH_ARTWORK,
        ):
            if state in (ProviderState.enabled_unconfigured, ProviderState.enabled_expired_unrefreshable):
                return False, f"state={state.value}"
            if not (has_access_token or has_refresh_token):
                return False, "no usable auth"
            return True, f"state={state.value}"

    if provider == "qobuz":
        if capability in (
            Capability.METADATA_FETCH_TRACK_BY_ID,
            Capability.METADATA_SEARCH_BY_TEXT,
        ):
            return True, "scaffold (unvalidated)"
        return False, "not supported by scaffold"

    if provider == "reccobeats":
        if capability in (
            Capability.METADATA_FETCH_TRACK_BY_ID,
            Capability.METADATA_SEARCH_BY_ISRC,
        ):
            return True, f"state={state.value}"
        return False, "not supported by provider"

    return False, "capability availability rule not defined"


class MetadataRouter:
    def __init__(
        self,
        *,
        provider_names: list[str],
        activation: ProviderActivationConfig,
        token_manager: TokenManager,
    ) -> None:
        self.provider_names = list(provider_names)
        self.activation = activation
        self.token_manager = token_manager

    def decisions_for(self, capability: Capability) -> list[CapabilityDecision]:
        decisions: list[CapabilityDecision] = []
        for name in self.provider_names:
            if not _supports_capability(name, capability):
                decisions.append(CapabilityDecision(provider=name, allowed=False, reason="capability not supported"))
                continue

            status = resolve_provider_status(name, activation=self.activation, token_manager=self.token_manager)
            allowed, reason = _capability_available_for_state(
                provider=name,
                capability=capability,
                state=status.state,
                has_access_token=status.has_access_token,
                has_refresh_token=status.has_refresh_token,
                metadata_usable=status.metadata_usable,
            )
            decisions.append(CapabilityDecision(provider=name, allowed=allowed, reason=reason))
        return decisions

    def provider_names_for(self, capability: Capability, *, log: Callable[[str], None] | None = None) -> list[str]:
        selected: list[str] = []
        for decision in self.decisions_for(capability):
            if decision.allowed:
                selected.append(decision.provider)
                continue
            if log is not None:
                log(f"Skip {decision.provider} for {capability.value}: {decision.reason}")
        return selected

    def first_provider_name_for(
        self,
        capability: Capability,
        *,
        log: Callable[[str], None] | None = None,
    ) -> str:
        names = self.provider_names_for(capability, log=log)
        if not names:
            raise CapabilityUnavailableError(f"No provider can satisfy capability: {capability.value}")
        return names[0]
