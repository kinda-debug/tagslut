"""
Track identity resolution chain.

Resolution priority:
  1. ISRC              (canonical_isrc column)
  2. Beatport ID       (beatport_id column)
  3. Tidal ID          (tidal_id column)
  4. Qobuz ID          (qobuz_id column)
  5. Fuzzy match       (artist + title + duration ±2s via rapidfuzz)
"""
import sqlite3
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz


@dataclass
class TrackIntent:
    """
    Represents a track the user intends to acquire (from a URL/playlist).
    Not yet on disk. All fields optional — populated from provider metadata.
    """

    title: Optional[str] = None
    artist: Optional[str] = None
    duration_s: Optional[float] = None
    isrc: Optional[str] = None
    beatport_id: Optional[str] = None
    tidal_id: Optional[str] = None
    qobuz_id: Optional[str] = None
    # Quality of the candidate (from provider API)
    bit_depth: Optional[int] = None
    sample_rate: Optional[int] = None
    bitrate: Optional[int] = None


@dataclass
class ResolutionResult:
    """
    Result of resolving a TrackIntent against the local inventory.
    """

    intent: TrackIntent
    # One of: "new", "upgrade", "skip"
    action: str
    # Path of existing file if found, else None
    existing_path: Optional[str] = None
    existing_quality_rank: Optional[int] = None
    candidate_quality_rank: Optional[int] = None
    match_method: Optional[str] = None  # "isrc", "beatport_id", "fuzzy", None
    match_score: Optional[float] = None


FUZZY_THRESHOLD = 88  # rapidfuzz score 0-100
DURATION_TOLERANCE_S = 2.0  # seconds


class IdentityResolver:
    """
    Resolves TrackIntent objects against a tagslut SQLite inventory.

    Usage:
        resolver = IdentityResolver(conn)
        result = resolver.resolve(intent, candidate_rank=3)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def resolve(self, intent: TrackIntent, candidate_rank: int) -> ResolutionResult:
        """
        Attempt to find a matching existing file for the given intent.
        Returns a ResolutionResult with action="new", "upgrade", or "skip".
        """
        existing = self._find_existing(intent)
        if existing is None:
            return ResolutionResult(
                intent=intent,
                action="new",
                candidate_quality_rank=candidate_rank,
            )

        existing_path, existing_rank, method, score = existing
        from tagslut.core.quality import is_upgrade

        if is_upgrade(current_rank=existing_rank, candidate_rank=candidate_rank):
            action = "upgrade"
        else:
            action = "skip"

        return ResolutionResult(
            intent=intent,
            action=action,
            existing_path=existing_path,
            existing_quality_rank=existing_rank,
            candidate_quality_rank=candidate_rank,
            match_method=method,
            match_score=score,
        )

    def _find_existing(
        self, intent: TrackIntent
    ) -> Optional[tuple[str, int, str, Optional[float]]]:
        """
        Returns (path, quality_rank, match_method, score) or None.
        """
        # 1. ISRC
        if intent.isrc:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE canonical_isrc = ? LIMIT 1",
                (intent.isrc,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "isrc", 100.0)

        # 2. Beatport ID
        if intent.beatport_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE beatport_id = ? LIMIT 1",
                (intent.beatport_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "beatport_id", 100.0)

        # 3. Tidal ID
        if intent.tidal_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE tidal_id = ? LIMIT 1",
                (intent.tidal_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "tidal_id", 100.0)

        # 4. Qobuz ID
        if intent.qobuz_id:
            row = self._conn.execute(
                "SELECT path, quality_rank FROM files WHERE qobuz_id = ? LIMIT 1",
                (intent.qobuz_id,),
            ).fetchone()
            if row and row[1] is not None:
                return (row[0], row[1], "qobuz_id", 100.0)

        # 5. Fuzzy: artist + title + duration
        if intent.artist and intent.title:
            return self._fuzzy_match(intent)

        return None

    def _fuzzy_match(
        self, intent: TrackIntent
    ) -> Optional[tuple[str, int, str, float]]:
        """
        Fuzzy match by artist + title using rapidfuzz, with optional duration gate.
        Only returns a match if score >= FUZZY_THRESHOLD.
        """
        query = """
            SELECT path, quality_rank,
                   canonical_artist, canonical_title, duration
            FROM files
            WHERE canonical_artist IS NOT NULL
              AND canonical_title IS NOT NULL
              AND quality_rank IS NOT NULL
        """
        rows = self._conn.execute(query).fetchall()
        best_score = 0.0
        best_row = None

        search_str = f"{intent.artist} {intent.title}".lower()
        for row in rows:
            candidate_str = f"{row[2]} {row[3]}".lower()
            score = fuzz.token_sort_ratio(search_str, candidate_str)
            if score > best_score:
                # Duration gate: if both have duration, enforce tolerance
                if intent.duration_s and row[4]:
                    if abs(intent.duration_s - row[4]) > DURATION_TOLERANCE_S:
                        continue
                best_score = score
                best_row = row

        if best_row and best_score >= FUZZY_THRESHOLD:
            return (best_row[0], best_row[1], "fuzzy", best_score)
        return None
