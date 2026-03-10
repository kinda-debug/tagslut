"""Phase 2 classification seam for v3 identity workflows.

This module intentionally exposes only stable import contracts.
It does not implement any classification policy.
"""

from __future__ import annotations

from typing import NamedTuple


class ClassificationCandidate(NamedTuple):
    identity_key: str
    canonical_artist: str | None
    canonical_title: str | None
    canonical_bpm: float | None
    canonical_key: str | None
    canonical_genre: str | None
    canonical_sub_genre: str | None


class Phase2ClassificationPolicy:
    """Placeholder interface for future Phase 2 policy logic."""

    def classify(self, candidate: ClassificationCandidate) -> str:
        raise NotImplementedError("Phase 2 classification policy is not implemented")
