from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
import unicodedata
from pathlib import Path
from typing import Any, Literal

import yaml

log = logging.getLogger(__name__)
_OVERRIDE_CACHE: dict[str, dict[str, dict[str, Any]]] | None = None

DEFAULT_DJ_GENRES: tuple[str, ...] = (
    "house",
    "tech house",
    "techno",
    "melodic house & techno",
    "indie dance",
)
DEFAULT_ANTI_DJ_GENRES: tuple[str, ...] = (
    "classical",
    "spoken word",
    "ambient",
    "pop",
)


@dataclass(frozen=True)
class DjCurationConfig:
    duration_min: int = 180
    duration_max: int = 720
    bpm_min: int = 100
    bpm_max: int = 175
    bpm_optimal_min: int = 120
    bpm_optimal_max: int = 135
    score_safe_min: int = 4
    score_block_max: int = -2
    artist_blocklist: frozenset[str] = field(default_factory=frozenset)
    artist_reviewlist: frozenset[str] = field(default_factory=frozenset)
    genre_filters: tuple[str, ...] = field(default_factory=tuple)
    dj_genres: tuple[str, ...] = field(default_factory=lambda: DEFAULT_DJ_GENRES)
    anti_dj_genres: tuple[str, ...] = field(default_factory=lambda: DEFAULT_ANTI_DJ_GENRES)
    genre_demote_mult: dict[str, float] = field(default_factory=dict)


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


def _normalize_path(value: str) -> str:
    """Normalize paths for matching (casefold + unicode normalization)."""
    return unicodedata.normalize("NFD", value.strip().lower())


def _override_key(artist: str, title: str) -> str:
    return f"{_normalize(artist)}|{_normalize(title)}"


def _load_track_overrides() -> dict[str, dict[str, dict[str, Any]]]:
    global _OVERRIDE_CACHE
    if _OVERRIDE_CACHE is not None:
        return _OVERRIDE_CACHE

    overrides_path = Path("config/dj/track_overrides.csv")
    by_path: dict[str, dict[str, Any]] = {}
    by_artist_title: dict[str, dict[str, Any]] = {}

    if not overrides_path.exists():
        _OVERRIDE_CACHE = {"by_path": by_path, "by_artist_title": by_artist_title}
        return _OVERRIDE_CACHE

    import csv

    with overrides_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row:
                continue
            if row[0].strip().startswith("#"):
                continue
            # Expected columns: path, artist, title, verdict, reason, crate
            if len(row) < 6:
                row = list(row) + [""] * (6 - len(row))
            path, artist, title, verdict, reason, crate = [cell.strip() for cell in row[:6]]
            if not artist or not title or not verdict:
                continue
            entry = {
                "path": path,
                "artist": artist,
                "title": title,
                "verdict": verdict.lower(),
                "reason": reason,
                "crate": crate,
            }
            if path:
                by_path[_normalize_path(path)] = entry
            by_artist_title[_override_key(artist, title)] = entry

    _OVERRIDE_CACHE = {"by_path": by_path, "by_artist_title": by_artist_title}
    return _OVERRIDE_CACHE


def resolve_track_override(
    *,
    path: str | None = None,
    artist: str | None = None,
    title: str | None = None,
) -> dict[str, Any] | None:
    overrides = _load_track_overrides()
    if path:
        entry = overrides["by_path"].get(_normalize_path(path))
        if entry is not None:
            return entry
    if artist and title:
        return overrides["by_artist_title"].get(_override_key(artist, title))
    return None


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
    bpm_min = int(rules.get("bpm_min", 100))
    bpm_max = int(rules.get("bpm_max", 175))
    bpm_optimal_min = int(rules.get("bpm_optimal_min", 120))
    bpm_optimal_max = int(rules.get("bpm_optimal_max", 135))
    score_safe_min = int(rules.get("score_safe_min", 4))
    score_block_max = int(rules.get("score_block_max", -2))

    dj_genres = rules.get("dj_genres")
    genres_allow = rules.get("genres_allow")
    if dj_genres is None and genres_allow is not None:
        merged = list(DEFAULT_DJ_GENRES)
        for genre in genres_allow:
            if genre not in merged:
                merged.append(genre)
        dj_genres = merged
    if dj_genres is None:
        dj_genres = list(DEFAULT_DJ_GENRES)
    anti_dj_genres = rules.get("anti_dj_genres") or list(DEFAULT_ANTI_DJ_GENRES)

    # Per-genre demotion multipliers override the flat anti-DJ penalty.
    raw_demote = rules.get("genre_demote_mult") or {}
    genre_demote_mult: dict[str, float] = {
        _normalize(k): float(v) for k, v in raw_demote.items()
    }

    return DjCurationConfig(
        duration_min=int(rules.get("duration_min", 180)),
        duration_max=int(rules.get("duration_max", 720)),
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        bpm_optimal_min=bpm_optimal_min,
        bpm_optimal_max=bpm_optimal_max,
        score_safe_min=score_safe_min,
        score_block_max=score_block_max,
        artist_blocklist=_load_list_file(blocklist_path) if blocklist_path else frozenset(),
        artist_reviewlist=_load_list_file(reviewlist_path) if reviewlist_path else frozenset(),
        genre_filters=tuple(rules.get("genre_filters", [])),
        dj_genres=tuple(dj_genres),
        anti_dj_genres=tuple(anti_dj_genres),
        genre_demote_mult=genre_demote_mult,
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
        path_value = str(track.get("path") or "").strip()
        artist_value = str(track.get("artist") or "").strip()
        title_value = str(track.get("title") or "").strip()
        override = resolve_track_override(path=path_value, artist=artist_value, title=title_value)

        if override:
            verdict = override.get("verdict")
            crate = override.get("crate")
            if verdict == "safe":
                result.passed.append({**track, "_verdict": "safe", "crate": crate})
            elif verdict == "block":
                result.rejected_blocklist.append(
                    {
                        **track,
                        "_verdict": "block",
                        "_rejection_reason": "track_override",
                        "crate": crate,
                    }
                )
            elif verdict == "review":
                result.flagged_reviewlist.append(
                    {
                        **track,
                        "_verdict": "review",
                        "_flag_reason": "track_override",
                        "crate": crate,
                    }
                )
                result.passed.append({**track, "_verdict": "review", "crate": crate})
            else:
                result.passed.append({**track, "_verdict": verdict or "unknown", "crate": crate})
            continue

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


@dataclass(frozen=True)
class DjScoreResult:
    track: dict[str, Any]
    score: int
    reasons: list[str]
    decision: Literal["safe", "block", "review"]


def _normalize_genre(value: str) -> str:
    return _normalize(value)


def calculate_dj_score(
    track: dict[str, Any],
    config: DjCurationConfig,
    library_remixers: set[str],
) -> DjScoreResult:
    score = 0
    reasons: list[str] = []

    title_lower = str(track.get("title") or "").lower()
    bpm = track.get("bpm") or 0
    duration = track.get("duration_sec") or 0

    if config.bpm_optimal_min <= bpm <= config.bpm_optimal_max:
        score += 3
        reasons.append("optimal BPM")
    elif config.bpm_min <= bpm <= config.bpm_max:
        pass
    else:
        if bpm:
            score -= 2
            reasons.append("BPM out of DJ range")

    if 240 <= duration <= 480:
        score += 1
        reasons.append("ideal duration")
    elif duration and duration < 120:
        score -= 2
        reasons.append("too short")
    elif duration and duration > 720:
        score -= 2
        reasons.append("too long")

    remixer = str(track.get("remixer") or "").strip().lower()
    if any(kw in title_lower for kw in ["remix", "edit", "bootleg"]) and remixer:
        if remixer in library_remixers:
            score += 2
            reasons.append("trusted remix")

    genre = _normalize_genre(str(track.get("genre") or ""))
    dj_genres = {_normalize_genre(g) for g in config.dj_genres}
    anti_dj = {_normalize_genre(g) for g in config.anti_dj_genres}
    if any(g in genre for g in dj_genres):
        score += 2
        reasons.append("DJ genre")
    if any(g in genre for g in anti_dj):
        # Apply per-genre multiplier if present, else flat -3
        matched_anti = [g for g in anti_dj if g in genre]
        if config.genre_demote_mult and matched_anti:
            # Use the strongest (most negative) multiplier that matches
            penalties = []
            for g in matched_anti:
                mult = config.genre_demote_mult.get(g)
                if mult is not None:
                    penalties.append(mult)
            if penalties:
                penalty = min(penalties)  # most negative wins
                score += int(penalty)
                reasons.append(f"anti-DJ genre ({penalty:+.1f})")
            else:
                score -= 3
                reasons.append("anti-DJ genre")
        else:
            score -= 3
            reasons.append("anti-DJ genre")

    decision: Literal["safe", "block", "review"]
    if score >= config.score_safe_min:
        decision = "safe"
    elif score <= config.score_block_max:
        decision = "block"
    else:
        decision = "review"

    return DjScoreResult(track=track, score=score, reasons=reasons, decision=decision)
