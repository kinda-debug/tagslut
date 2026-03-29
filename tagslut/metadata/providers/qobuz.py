"""Qobuz provider scaffold (off by default).

This is a capability-scaffold only: it is activation-gated and does not
participate in identity_key derivation.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from tagslut.metadata.capabilities import Capability
from tagslut.metadata.models.types import ProviderTrack
from tagslut.metadata.providers.base import AbstractProvider

logger = logging.getLogger("tagslut.metadata.providers.qobuz")


class QobuzProvider(AbstractProvider):
    name = "qobuz"
    supports_isrc_search = False
    capabilities = {
        Capability.METADATA_FETCH_TRACK_BY_ID,
        Capability.METADATA_SEARCH_BY_TEXT,
    }

    def _get_default_headers(self) -> Dict[str, str]:
        return {"Accept": "application/json"}

    def fetch_by_id(self, track_id: str) -> Optional[ProviderTrack]:
        logger.warning("qobuz scaffold: fetch_by_id not implemented (track_id=%s)", track_id)
        return None

    def search(self, query: str, limit: int = 10) -> List[ProviderTrack]:
        logger.warning("qobuz scaffold: search not implemented (query=%s limit=%d)", query, limit)
        return []

