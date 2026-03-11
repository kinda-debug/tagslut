from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from tagslut.library.models import Track, TrackAlias, TrackFile
from tagslut.library.repositories import get_tracks_for_matching

MIN_SCORE_THRESHOLD = 0.85
MIN_REVIEW_SCORE = 0.50
PRIMARY_DURATION_TOLERANCE_MS = 2000
FALLBACK_DURATION_TOLERANCE_MS = 5000
ALIAS_BONUS = 0.15
FINGERPRINT_SCORE = 0.95

_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")
_MIX_KEYWORD_RE = re.compile(
    r"\b("
    r"mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended"
    r")\b",
    re.IGNORECASE,
)
_TITLE_SUFFIX_RE = re.compile(
    r"""
    ^
    (?P<base>.*?)
    (?:
        \s*(?:\(|\[)\s*(?P<bracketed>[^)\]]*?\b(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended)\b[^)\]]*)\s*(?:\)|\])
        |
        \s*[-:]\s*(?P<dashed>.*?\b(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended)\b.*)
        |
        \s+(?P<trailing>\b(?:.*(?:mix|remix|version|edit|dub|rework|vip|instrumental|radio|club|extended).*)\b)
    )?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)
_FINGERPRINT_ALIAS_TYPES = (
    "fingerprint",
    "acoustic_fingerprint",
    "file_hash",
    "file_hash_sha256",
)


@dataclass(frozen=True)
class TrackQuery:
    title: str
    artist: str
    duration_ms: int | None = None
    rekordbox_id: str | None = None
    file_path: str | None = None
    isrc: str | None = None
    fingerprint: str | None = None


@dataclass
class MatchResult:
    track: Track | None
    score: float
    reasons: list[str] = field(default_factory=list)
    alias_hit: bool = False


@dataclass(frozen=True)
class _NormalizedTitle:
    base: str
    mix: str


@dataclass(frozen=True)
class _PreparedQuery:
    original: TrackQuery
    title: _NormalizedTitle
    artist: str
    path: str
    path_stem: str


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    lowered = value.casefold()
    lowered = _PUNCTUATION_RE.sub(" ", lowered)
    lowered = _WHITESPACE_RE.sub(" ", lowered)
    return lowered.strip()


def _split_title_mix(title: str | None, explicit_mix: str | None = None) -> _NormalizedTitle:
    if explicit_mix:
        return _NormalizedTitle(
            base=_normalize_text(title),
            mix=_normalize_text(explicit_mix),
        )

    raw_title = title or ""
    match = _TITLE_SUFFIX_RE.match(raw_title.strip())
    if match is None:
        return _NormalizedTitle(base=_normalize_text(raw_title), mix="")

    mix_value = (
        match.group("bracketed")
        or match.group("dashed")
        or match.group("trailing")
        or ""
    )
    base_value = match.group("base") or raw_title
    if mix_value and not _MIX_KEYWORD_RE.search(mix_value):
        mix_value = ""
        base_value = raw_title
    return _NormalizedTitle(
        base=_normalize_text(base_value),
        mix=_normalize_text(mix_value),
    )


def _sequence_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _combine_title_similarity(
    query_title: _NormalizedTitle,
    track_title: _NormalizedTitle,
) -> float:
    base_similarity = _sequence_similarity(query_title.base, track_title.base)
    if not query_title.mix and not track_title.mix:
        return base_similarity
    if query_title.mix and track_title.mix:
        mix_similarity = _sequence_similarity(query_title.mix, track_title.mix)
    else:
        mix_similarity = 0.0
    return (base_similarity * 0.85) + (mix_similarity * 0.15)


def _track_duration_ms(track: Track) -> int | None:
    preferred = next(
        (
            track_file
            for track_file in track.files
            if (
                track_file.active
                and track_file.is_preferred
                and track_file.duration_ms is not None
            )
        ),
        None,
    )
    if preferred is not None:
        return preferred.duration_ms
    fallback = next(
        (
            track_file
            for track_file in track.files
            if track_file.active and track_file.duration_ms is not None
        ),
        None,
    )
    return fallback.duration_ms if fallback is not None else None


def _prepare_query(query: TrackQuery) -> _PreparedQuery:
    normalized_path = str(Path(query.file_path).expanduser()) if query.file_path else ""
    path_stem = _normalize_text(Path(normalized_path).stem) if normalized_path else ""
    return _PreparedQuery(
        original=query,
        title=_split_title_mix(query.title),
        artist=_normalize_text(query.artist),
        path=_normalize_text(normalized_path),
        path_stem=path_stem,
    )


class TrackMatcher:
    # Future upload/filename parsing flows can call this matcher after
    # extracting title/artist, once a canonical linking path exists.

    def __init__(self, session: Session):
        self._session = session

    def match(self, query: TrackQuery) -> MatchResult:
        prepared = _prepare_query(query)

        external_match = self._match_external_id(prepared.original)
        if external_match is not None:
            return external_match

        fingerprint_match = self._match_fingerprint(prepared.original)
        if fingerprint_match is not None:
            return fingerprint_match

        best_result = MatchResult(
            track=None,
            score=0.0,
            reasons=["no candidates"],
            alias_hit=False,
        )

        for track in get_tracks_for_matching(self._session):
            candidate = self._score_candidate(track, prepared)
            if candidate.score > best_result.score:
                best_result = candidate

        if best_result.track is None or best_result.score < MIN_REVIEW_SCORE:
            return MatchResult(
                track=None,
                score=0.0,
                reasons=["no match found"],
                alias_hit=False,
            )
        return best_result

    def _match_external_id(self, query: TrackQuery) -> MatchResult | None:
        if query.rekordbox_id:
            track = self._lookup_alias_track("rekordbox_track_id", query.rekordbox_id)
            if track is not None:
                return MatchResult(
                    track=track,
                    score=1.0,
                    reasons=["exact rekordbox_id alias hit"],
                    alias_hit=True,
                )

        if query.isrc:
            track = self._lookup_alias_track("isrc", query.isrc)
            if track is not None:
                return MatchResult(
                    track=track,
                    score=1.0,
                    reasons=["exact isrc alias hit"],
                    alias_hit=True,
                )
        return None

    def _match_fingerprint(self, query: TrackQuery) -> MatchResult | None:
        if not query.fingerprint:
            return None

        alias_track = self._session.scalar(
            select(Track)
            .join(TrackAlias, TrackAlias.track_id == Track.id)
            .where(
                Track.status == "active",
                TrackAlias.alias_type.in_(_FINGERPRINT_ALIAS_TYPES),
                TrackAlias.value == query.fingerprint,
            )
            .limit(1)
        )
        if alias_track is not None:
            return MatchResult(
                track=alias_track,
                score=1.0,
                reasons=["exact fingerprint alias hit"],
                alias_hit=True,
            )

        file_track = self._session.scalar(
            select(Track)
            .join(TrackFile, TrackFile.track_id == Track.id)
            .where(
                Track.status == "active",
                TrackFile.active.is_(True),
                or_(
                    TrackFile.acoustic_fingerprint == query.fingerprint,
                    TrackFile.file_hash_sha256 == query.fingerprint,
                ),
            )
            .limit(1)
        )
        if file_track is not None:
            return MatchResult(
                track=file_track,
                score=FINGERPRINT_SCORE,
                reasons=["exact fingerprint/file hash track file hit"],
                alias_hit=False,
            )
        return None

    def _lookup_alias_track(self, alias_type: str, value: str) -> Track | None:
        return self._session.scalar(
            select(Track)
            .join(TrackAlias, TrackAlias.track_id == Track.id)
            .where(
                Track.status == "active",
                TrackAlias.alias_type == alias_type,
                TrackAlias.value == value,
            )
            .limit(1)
        )

    def _score_candidate(self, track: Track, query: _PreparedQuery) -> MatchResult:
        track_title = _split_title_mix(track.canonical_title, track.canonical_mix_name)
        title_similarity = _combine_title_similarity(query.title, track_title)
        artist_similarity = _sequence_similarity(
            query.artist,
            _normalize_text(track.canonical_artist_credit),
        )
        reasons = [
            f"title_similarity={title_similarity:.2f}",
            f"artist_similarity={artist_similarity:.2f}",
        ]

        duration_score: float | None = None
        if query.original.duration_ms is not None:
            duration_score = self._duration_score(track, query.original.duration_ms, reasons)
            if duration_score is None:
                return MatchResult(
                    track=None,
                    score=0.0,
                    reasons=reasons + ["duration outside fallback"],
                    alias_hit=False,
                )

        alias_hit, alias_reasons = self._alias_rescue(track, query)
        reasons.extend(alias_reasons)

        score = self._composite_score(
            title_similarity=title_similarity,
            artist_similarity=artist_similarity,
            duration_score=duration_score,
            alias_hit=alias_hit,
        )
        reasons.append(f"score={score:.2f}")
        return MatchResult(track=track, score=score, reasons=reasons, alias_hit=alias_hit)

    def _duration_score(
        self,
        track: Track,
        query_duration_ms: int,
        reasons: list[str],
    ) -> float | None:
        candidate_duration_ms = _track_duration_ms(track)
        if candidate_duration_ms is None:
            reasons.append("duration unavailable")
            return 0.5

        delta_ms = abs(candidate_duration_ms - query_duration_ms)
        reasons.append(f"duration_delta_ms={delta_ms}")
        if delta_ms <= PRIMARY_DURATION_TOLERANCE_MS:
            reasons.append("duration within primary tolerance")
            return 1.0
        if delta_ms <= FALLBACK_DURATION_TOLERANCE_MS:
            ratio = (delta_ms - PRIMARY_DURATION_TOLERANCE_MS) / (
                FALLBACK_DURATION_TOLERANCE_MS - PRIMARY_DURATION_TOLERANCE_MS
            )
            score = 1.0 - (ratio * 0.35)
            reasons.append("duration within fallback tolerance")
            return score
        return None

    def _composite_score(
        self,
        *,
        title_similarity: float,
        artist_similarity: float,
        duration_score: float | None,
        alias_hit: bool,
    ) -> float:
        title_weight = 0.55
        artist_weight = 0.30
        duration_weight = 0.15 if duration_score is not None else 0.0
        total_weight = title_weight + artist_weight + duration_weight
        if total_weight == 0:
            return 0.0

        score = (
            (title_similarity * title_weight)
            + (artist_similarity * artist_weight)
            + ((duration_score or 0.0) * duration_weight)
        ) / total_weight
        if alias_hit:
            score = min(1.0, score + ALIAS_BONUS)
        return score

    def _alias_rescue(self, track: Track, query: _PreparedQuery) -> tuple[bool, list[str]]:
        query_strings = [
            value
            for value in (
                query.title.base,
                query.artist,
                query.path,
                query.path_stem,
                _normalize_text(f"{query.original.artist} {query.original.title}"),
            )
            if value
        ]
        reasons: list[str] = []

        for alias in track.aliases:
            normalized_alias = _normalize_text(alias.value)
            if not normalized_alias:
                continue
            if normalized_alias in query_strings:
                reasons.append(f"alias rescue exact hit ({alias.alias_type})")
                return True, reasons
            similarity = max(
                (
                    _sequence_similarity(normalized_alias, candidate)
                    for candidate in query_strings
                ),
                default=0.0,
            )
            if similarity >= 0.92:
                reasons.append(
                    f"alias rescue fuzzy hit ({alias.alias_type}, similarity={similarity:.2f})"
                )
                return True, reasons

        return False, reasons
