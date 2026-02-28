"""
ISRC candidate extraction and normalization.

Design decisions:
- Multiple ISRCs in one tag value are all extracted.
- Invalid/garbage values are silently dropped.
- Results are deduplicated preserving first-seen order.
- This module does NOT set a canonical ISRC — that requires confidence gating.
"""
import re
from typing import Iterable, List

# 12-char compact form: 2-letter country + 3-char registrant + 7 digits
_ISRC_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{3}[0-9]{7})\b")


def normalize_isrc(value: str) -> str:
    """Strip dashes, spaces, uppercase. Does not validate format."""
    return value.upper().replace("-", "").replace(" ", "")


def extract_isrc_candidates(values: Iterable[str]) -> List[str]:
    """
    Extract all valid ISRC candidates from an iterable of strings.

    Handles:
    - Multi-valued tag lists (each value is a separate string)
    - Single string containing multiple ISRCs
    - Strings with dashes or spaces in the ISRC
    - Garbage (ignored silently)

    Returns unique candidates in first-seen order.
    """
    out: List[str] = []
    seen: set = set()
    for v in values:
        if not v:
            continue
        # Normalize before matching
        norm = str(v).upper().replace("-", "").replace("/", " ")
        for m in _ISRC_RE.finditer(norm):
            cand = m.group(1)
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out
