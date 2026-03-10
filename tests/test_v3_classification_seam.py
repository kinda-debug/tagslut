from __future__ import annotations

import pytest

from tagslut.storage.v3 import ClassificationCandidate, Phase2ClassificationPolicy


def test_phase2_classification_seam_imports_cleanly() -> None:
    candidate = ClassificationCandidate(
        identity_key="isrc:USAAA1111111",
        canonical_artist="Artist",
        canonical_title="Title",
        canonical_bpm=122.0,
        canonical_key="8A",
        canonical_genre="House",
        canonical_sub_genre="Deep House",
    )

    assert candidate.identity_key == "isrc:USAAA1111111"
    assert candidate.canonical_bpm == 122.0

    policy = Phase2ClassificationPolicy()
    with pytest.raises(NotImplementedError, match="not implemented"):
        policy.classify(candidate)
