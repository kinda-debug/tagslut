"""Miscellaneous helper functions for Audio Suite."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Iterable, Tuple


def similarity(a: str, b: str) -> float:
    """Return a ratio between 0 and 1 representing the similarity of two strings.

    This function wraps :class:`difflib.SequenceMatcher` to compute a quick
    similarity score.  It is used by the matching engine to rank potential
    matches.  A higher score indicates greater similarity.
    """
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def pick_best_match(query: str, candidates: Iterable[str]) -> Tuple[str, float]:
    """Return the candidate with the highest similarity to the query.

    If ``candidates`` is empty, returns ``("", 0.0)``.
    """
    best_score = 0.0
    best_candidate = ""
    for candidate in candidates:
        score = similarity(query, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_candidate, best_score