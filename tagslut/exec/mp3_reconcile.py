"""MP3 reconcile helpers (DJ pipeline Stage 2).

This module intentionally contains the matching/normalization utilities used by:
- `tagslut mp3 reconcile` (live tag scan)
- `reconcile_mp3_scan()` (CSV scan reconcile)

Normalization must be compatible with the normalization used when writing
`track_identity.artist_norm` / `track_identity.title_norm` rows in v3.
"""

from __future__ import annotations

import importlib
import re
from typing import Callable, cast

_ISRC_SPLIT_RE = re.compile(r"[;,/|\s]+")
_ISRC_STRIP_RE = re.compile(r"[\s-]+")

_FEAT_BRACKET_RE = re.compile(
    r"\s*(?:\(|\[)\s*(?:feat\.?|ft\.?|featuring|with)\b.*?(?:\)|\])\s*",
    re.IGNORECASE,
)
_FEAT_TRAIL_RE = re.compile(
    r"\s+(?:feat\.?|ft\.?|featuring|with)\b.*$",
    re.IGNORECASE,
)
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)

_MIX_KEYWORD_RE = re.compile(
    r"\b("
    r"mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended|bootleg|live"
    r")\b",
    re.IGNORECASE,
)
_TITLE_SUFFIX_RE = re.compile(
    r"""
    ^
    (?P<base>.*?)
    (?:
        \s*(?:\(|\[)\s*(?P<bracketed>[^)\]]*?\b(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended|bootleg|live)\b[^)\]]*)\s*(?:\)|\])
        |
        \s*[-:]\s*(?P<dashed>.*?\b(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended|bootleg|live)\b.*)
        |
        \s+(?P<trailing>\b(?:.*(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended|bootleg|live).*)\b)
    )?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_isrc(value: str | None) -> str:
    """Normalize ISRC-ish strings for case-insensitive matching.

    - Strips surrounding whitespace
    - Takes the first token when multiple are present
    - Upper-cases
    - Removes whitespace and hyphens so tags like "US-ABC-1234567" still match
    """
    text = (value or "").strip()
    if not text:
        return ""
    token = ""
    for part in _ISRC_SPLIT_RE.split(text):
        part = part.strip()
        if part:
            token = part
            break
    if not token:
        return ""
    token = token.upper()
    token = _ISRC_STRIP_RE.sub("", token)
    return token.strip()


def _load_identity_norm_name() -> Callable[[object], str | None]:
    module = importlib.import_module("tagslut.storage.v3.identity_service")
    fn = getattr(module, "_norm_name", None)
    if not callable(fn):
        raise RuntimeError("tagslut.storage.v3.identity_service._norm_name not found")
    return cast(Callable[[object], str | None], fn)


def _identity_norm_name(value: str | None) -> str:
    """Call the v3 identity normalization used for artist_norm/title_norm."""
    if not value:
        return ""
    try:
        fn = _load_identity_norm_name()
        normalized = fn(value)
        return normalized or ""
    except Exception:
        return " ".join(value.strip().lower().split())


def _strip_feat(text: str) -> str:
    text = _FEAT_BRACKET_RE.sub(" ", text)
    text = _FEAT_TRAIL_RE.sub("", text)
    return " ".join(text.split()).strip()


def _strip_title_mix_suffix(text: str) -> str:
    match = _TITLE_SUFFIX_RE.match(text.strip())
    if match is None:
        return text
    mix_value = (
        match.group("bracketed")
        or match.group("dashed")
        or match.group("trailing")
        or ""
    )
    base_value = match.group("base") or text
    if mix_value and _MIX_KEYWORD_RE.search(mix_value):
        return base_value.strip()
    return text


def normalize_artist_for_match(value: str | None) -> str:
    text = _strip_feat((value or "").strip())
    text = _LEADING_ARTICLE_RE.sub("", text).strip()
    return _identity_norm_name(text)


def normalize_title_for_match(value: str | None) -> str:
    text = _strip_feat((value or "").strip())
    text = _strip_title_mix_suffix(text)
    text = _LEADING_ARTICLE_RE.sub("", text).strip()
    return _identity_norm_name(text)


def normalize_artist_title_pair(artist: str | None, title: str | None) -> tuple[str, str]:
    return (normalize_artist_for_match(artist), normalize_title_for_match(title))
