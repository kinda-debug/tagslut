from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DjCurationConfig:
    duration_min: int = 180
    duration_max: int = 720
    artist_blocklist: frozenset[str] = field(default_factory=frozenset)
    artist_reviewlist: frozenset[str] = field(default_factory=frozenset)
    genre_filters: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class CurationStats:
    total: int = 0
    passed: int = 0
    rejected_duration: int = 0
    rejected_blocklist: int = 0
    rejected_genre: int = 0
    flagged_reviewlist: int = 0


@dataclass
class CurationResult:
    passed: list[dict[str, Any]] = field(default_factory=list)
    rejected_duration: list[dict[str, Any]] = field(default_factory=list)
    rejected_blocklist: list[dict[str, Any]] = field(default_factory=list)
    rejected_genre: list[dict[str, Any]] = field(default_factory=list)
    flagged_reviewlist: list[dict[str, Any]] = field(default_factory=list)

    @property
    def stats(self) -> CurationStats:
        return CurationStats(
            total=len(self.passed)
            + len(self.rejected_duration)
            + len(self.rejected_blocklist)
            + len(self.rejected_genre),
            passed=len(self.passed),
            rejected_duration=len(self.rejected_duration),
            rejected_blocklist=len(self.rejected_blocklist),
            rejected_genre=len(self.rejected_genre),
            flagged_reviewlist=len(self.flagged_reviewlist),
        )


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _load_list_file(path: str) -> frozenset[str]:
    """Load a text file of names (one per line) into a normalized frozenset."""
    p = Path(path)
    if not p.exists():
        log.warning("List file not found: %s", path)
        return frozenset()
    lines = p.read_text(encoding="utf-8").splitlines()
    return frozenset(
        _normalize(line) for line in lines if line.strip() and not line.startswith("#")
    )


def load_dj_curation_config(path: str) -> DjCurationConfig:
    """Load DJ curation config from YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = data.get("rules", {}) if isinstance(data, dict) else {}

    blocklist_path = rules.get("artist_blocklist_path", "")
    reviewlist_path = rules.get("artist_reviewlist_path", "")

    return DjCurationConfig(
        duration_min=int(rules.get("duration_min", 180)),
        duration_max=int(rules.get("duration_max", 720)),
        artist_blocklist=_load_list_file(blocklist_path) if blocklist_path else frozenset(),
        artist_reviewlist=_load_list_file(reviewlist_path) if reviewlist_path else frozenset(),
        genre_filters=tuple(rules.get("genre_filters", [])),
    )


def filter_candidates(
    candidates: list[dict[str, Any]],
    config: DjCurationConfig,
) -> CurationResult:
    """Apply DJ curation rules to a list of track candidates.

    Each candidate dict must have:
    - duration_sec: float | None
    - artist: str
    - genre: str | None  (optional)

    Returns CurationResult with tracks sorted into buckets.
    """
    result = CurationResult()

    for track in candidates:
        artist_normalized = _normalize(str(track.get("artist", "")))

        if artist_normalized in config.artist_blocklist:
            result.rejected_blocklist.append({**track, "_rejection_reason": "artist_blocklist"})
            continue

        duration = track.get("duration_sec")
        if duration is not None:
            if duration < config.duration_min:
                result.rejected_duration.append(
                    {**track, "_rejection_reason": f"too_short_{duration:.0f}s"}
                )
                continue
            if duration > config.duration_max:
                result.rejected_duration.append(
                    {**track, "_rejection_reason": f"too_long_{duration:.0f}s"}
                )
                continue

        if config.genre_filters:
            genre = _normalize(str(track.get("genre", "") or ""))
            blocked_genre = next(
                (g for g in config.genre_filters if _normalize(g) in genre), None
            )
            if blocked_genre:
                result.rejected_genre.append(
                    {**track, "_rejection_reason": f"genre_filter:{blocked_genre}"}
                )
                continue

        if artist_normalized in config.artist_reviewlist:
            result.flagged_reviewlist.append({**track, "_flag_reason": "artist_reviewlist"})

        result.passed.append(track)

    return result
