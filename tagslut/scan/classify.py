"""Classification logic for scanner status and identity confidence."""

from typing import Dict, List, Optional, Tuple

from tagslut.scan.constants import (
    DURATION_ERROR_DELTA_S,
    DURATION_WARN_DELTA_S,
    IDENTITY_CONFIDENCE_ALBUM_YEAR,
    IDENTITY_CONFIDENCE_ARTIST_TITLE,
    IDENTITY_CONFIDENCE_BPM_VALID,
    IDENTITY_CONFIDENCE_DURATION_OK,
    IDENTITY_CONFIDENCE_FINGERPRINT,
    IDENTITY_CONFIDENCE_ISRC_SINGLE,
    IDENTITY_CONFIDENCE_KEY_VALID,
)


def compute_identity_confidence(
    raw_tags: Dict[str, List[str]],
    isrc_candidates: List[str],
    duration_delta: Optional[float],
    has_fingerprint: bool = False,
) -> int:
    """
    Compute instrumentation-only confidence score (0..100).
    No user input is considered.
    """
    score = 0

    # ISRC signal
    if len(isrc_candidates) == 1:
        score += IDENTITY_CONFIDENCE_ISRC_SINGLE
    # Multi-ISRC: no bonus (ambiguous)

    # Fingerprint
    if has_fingerprint:
        score += IDENTITY_CONFIDENCE_FINGERPRINT

    # Artist + title
    def _has(keys: List[str]) -> bool:
        return any(any(v.strip() for v in raw_tags.get(k, [])) for k in keys)

    if _has(["ARTIST", "TPE1", "artist", "albumartist"]) and _has(["TITLE", "TIT2", "title"]):
        score += IDENTITY_CONFIDENCE_ARTIST_TITLE

    # Album + year
    if _has(["ALBUM", "TALB", "album"]) and _has(["DATE", "TDRC", "year", "date"]):
        score += IDENTITY_CONFIDENCE_ALBUM_YEAR

    # BPM valid range
    for key in ["BPM", "TBPM", "bpm"]:
        vals = raw_tags.get(key, [])
        for value in vals:
            try:
                bpm = float(value)
                if 60 <= bpm <= 220:
                    score += IDENTITY_CONFIDENCE_BPM_VALID
                    break
            except (ValueError, TypeError):
                pass

    # Key present
    if _has(["INITIALKEY", "TKEY", "initialkey", "key"]):
        score += IDENTITY_CONFIDENCE_KEY_VALID

    # Duration coherent
    if duration_delta is not None and abs(duration_delta) < DURATION_WARN_DELTA_S:
        score += IDENTITY_CONFIDENCE_DURATION_OK

    return min(score, 100)


def classify_primary_status(
    has_tags_error: bool,
    decode_errors: List[str],
    duration_delta: Optional[float],
) -> Tuple[str, List[str]]:
    """
    Return (scan_status, flags[]).
    """
    flags: List[str] = []

    if has_tags_error or decode_errors:
        return "CORRUPT", flags

    if duration_delta is not None:
        if duration_delta < -DURATION_ERROR_DELTA_S:
            return "TRUNCATED", flags
        if duration_delta > DURATION_ERROR_DELTA_S:
            return "EXTENDED", flags
        if abs(duration_delta) > DURATION_WARN_DELTA_S:
            flags.append("DURATION_MISMATCH_WARN")

    return "CLEAN", flags
