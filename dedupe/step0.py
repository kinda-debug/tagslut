"""Step-0 ingestion helpers for canonical library selection."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


FORBIDDEN_CHARS = r'<>:"/\\|?*'
ERROR_SIGNATURES = (
    "LOST_SYNC",
    "BAD_HEADER",
    "END_OF_STREAM",
    "CRC mismatch",
)


@dataclass(slots=True)
class IntegrityResult:
    """Structured integrity outcome from a FLAC validation run."""

    status: str
    stderr_excerpt: str
    return_code: Optional[int]


@dataclass(slots=True)
class ScannedFile:
    """Aggregated metadata for a scanned FLAC file."""

    path: str
    content_hash: str
    streaminfo_md5: Optional[str]
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_depth: Optional[int]
    channels: Optional[int]
    tags: Mapping[str, Any]
    integrity: IntegrityResult


def _normalise_text(value: str) -> str:
    """Return NFC-normalised text for deterministic path generation."""

    return unicodedata.normalize("NFC", value.strip())


def _replace_forbidden(value: str) -> str:
    """Replace characters unsafe for filesystems."""

    return re.sub(rf"[{re.escape(FORBIDDEN_CHARS)}]", "_", value)


def sanitize_component(value: str, fallback: str) -> str:
    """Return a safe filename component with forbidden characters replaced."""

    cleaned = _replace_forbidden(_normalise_text(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or fallback


def parse_track_number(value: str | None) -> Optional[int]:
    """Parse track numbers like ``1`` or ``1/12`` into an integer."""

    if not value:
        return None
    match = re.match(r"(\d+)", str(value).strip())
    if not match:
        return None
    return int(match.group(1))


def parse_disc_number(value: str | None) -> Optional[int]:
    """Parse disc numbers like ``2`` or ``2/3`` into an integer."""

    if not value:
        return None
    match = re.match(r"(\d+)", str(value).strip())
    if not match:
        return None
    return int(match.group(1))


def parse_year(value: str | None) -> str:
    """Return a four-digit year derived from tag input."""

    if not value:
        return "0000"
    match = re.search(r"(\d{4})", str(value))
    return match.group(1) if match else "0000"


def extract_tag_value(tags: Mapping[str, Any], key: str) -> Optional[str]:
    """Return the first tag value for a key, normalising lists."""

    raw = tags.get(key)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return str(raw[0]) if raw else None
    return str(raw)


def extract_identity_hints(tags: Mapping[str, Any]) -> dict[str, Optional[str]]:
    """Extract identity hints from tag mappings."""

    lowered = {key.lower(): value for key, value in tags.items()}
    isrc = extract_tag_value(lowered, "isrc")
    track_mbid = extract_tag_value(lowered, "musicbrainz_trackid")
    release_mbid = extract_tag_value(lowered, "musicbrainz_albumid")
    artist = extract_tag_value(lowered, "artist")
    title = extract_tag_value(lowered, "title")
    album = extract_tag_value(lowered, "album")
    date = extract_tag_value(lowered, "date")
    track = extract_tag_value(lowered, "tracknumber") or extract_tag_value(lowered, "track")
    disc = extract_tag_value(lowered, "discnumber") or extract_tag_value(lowered, "disc")
    return {
        "isrc": isrc,
        "musicbrainz_track_id": track_mbid,
        "musicbrainz_release_id": release_mbid,
        "artist": artist,
        "title": title,
        "album": album,
        "date": date,
        "track_number": track,
        "disc_number": disc,
    }


def metadata_score(tags: Mapping[str, Any]) -> int:
    """Score metadata completeness for duplicate resolution."""

    hints = extract_identity_hints(tags)
    score_keys = ("artist", "title", "album", "date", "track_number", "disc_number")
    return sum(1 for key in score_keys if hints.get(key))


def encoder_score(tags: Mapping[str, Any]) -> int:
    """Score encoder/vendor tag stability for tie-breaking."""

    lowered = {key.lower(): value for key, value in tags.items()}
    score = 0
    for key in ("encoder", "vendor", "encoder_settings", "encoded_by"):
        if key in lowered and lowered[key]:
            score += 1
    return score


def duration_distance(duration: Optional[float], reference: Optional[float]) -> float:
    """Return absolute distance between duration and a reference."""

    if duration is None or reference is None:
        return float("inf")
    return abs(duration - reference)


def choose_canonical(candidates: Iterable[ScannedFile]) -> Optional[ScannedFile]:
    """Select the canonical file from valid candidates."""

    valid = [item for item in candidates if item.integrity.status == "pass"]
    if not valid:
        return None
    durations = [item.duration for item in valid if item.duration is not None]
    reference = sum(durations) / len(durations) if durations else None

    def _sort_key(item: ScannedFile) -> tuple:
        return (
            -(item.bit_depth or 0),
            -(item.sample_rate or 0),
            duration_distance(item.duration, reference),
            -metadata_score(item.tags),
            -encoder_score(item.tags),
            item.content_hash,
        )

    return sorted(valid, key=_sort_key)[0]


def build_canonical_path(tags: Mapping[str, Any]) -> str:
    """Build a canonical FLAC path from tag metadata."""

    hints = extract_identity_hints(tags)
    artist = sanitize_component(hints.get("artist") or "", "Unknown Artist")
    album = sanitize_component(hints.get("album") or "", "Unknown Album")
    title = sanitize_component(hints.get("title") or "", "Unknown Title")
    year = parse_year(hints.get("date"))
    track_number = parse_track_number(hints.get("track_number"))
    disc_number = parse_disc_number(hints.get("disc_number"))
    track_str = f"{track_number:02d}" if track_number is not None else "00"
    if disc_number is not None:
        track_str = f"{disc_number}-{track_str}"
    return f"{artist}/({year}) {album}/{track_str}. {title}.flac"


def confidence_score(tags: Mapping[str, Any]) -> float:
    """Estimate confidence for reacquire recommendations."""

    hints = extract_identity_hints(tags)
    score = 0.2
    if hints.get("artist"):
        score += 0.2
    if hints.get("title"):
        score += 0.2
    if hints.get("album"):
        score += 0.1
    if hints.get("isrc"):
        score += 0.3
    return min(score, 1.0)


def classify_integrity(stderr: str, return_code: Optional[int]) -> IntegrityResult:
    """Classify integrity based on stderr content and return code."""

    stderr_excerpt = stderr.strip()
    stderr_excerpt = stderr_excerpt[:500] if stderr_excerpt else ""
    upper = stderr.upper()
    for signature in ERROR_SIGNATURES:
        if signature.upper() in upper:
            return IntegrityResult(
                status="fail",
                stderr_excerpt=stderr_excerpt,
                return_code=return_code,
            )
    if return_code == 0:
        return IntegrityResult(
            status="pass",
            stderr_excerpt=stderr_excerpt,
            return_code=return_code,
        )
    return IntegrityResult(
        status="fail",
        stderr_excerpt=stderr_excerpt,
        return_code=return_code,
    )
