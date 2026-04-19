"""
Track identity resolution chain.

Resolution priority:
  1. Shared v3 resolver (strong evidence only; text creates review artifacts)
  2. ISRC              (isrc column; canonical_isrc fallback for legacy rows)
  3. Beatport ID       (beatport_id column)
  4. Tidal ID          (tidal_id column)
"""
import sqlite3
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from tagslut.storage.queries import get_file_by_isrc
from tagslut.storage.v3.resolver import ResolverInput, resolve_identity


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
        v3_existing = self._find_existing_v3(intent)
        if v3_existing is not None:
            return v3_existing

        # 1. ISRC
        if intent.isrc:
            row = get_file_by_isrc(self._conn, intent.isrc)
            if row and row[1] is not None:
                return (row[0], row[1], "isrc", 100.0)
            # Compatibility fallback for older rows that only populated canonical_isrc.
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

        # 4. Text-only evidence is review-only in v3. Keep legacy files as a
        # fallback for exact identifiers, but do not skip/upgrade on fuzzy text.
        if intent.artist and intent.title:
            resolve_identity(
                self._conn,
                ResolverInput(
                    isrc=intent.isrc,
                    provider_ids={
                        key: value
                        for key, value in {
                            "beatport_id": intent.beatport_id,
                            "tidal_id": intent.tidal_id,
                        }.items()
                        if value
                    },
                    artist=intent.artist,
                    title=intent.title,
                    duration_s=intent.duration_s,
                    source_system="legacy_identity_resolver",
                    source_ref=f"{intent.artist}|{intent.title}",
                ),
                persist=True,
                allow_text_auto_match=False,
            )

        return None

    def _find_existing_v3(
        self,
        intent: TrackIntent,
    ) -> Optional[tuple[str, int, str, Optional[float]]]:
        """
        Query v3 identity/preferred_asset first and return a file path when the
        shared resolver accepts strong evidence.
        """
        result = resolve_identity(
            self._conn,
            ResolverInput(
                isrc=intent.isrc,
                provider_ids={
                    key: value
                    for key, value in {
                        "beatport_id": intent.beatport_id,
                        "tidal_id": intent.tidal_id,
                    }.items()
                    if value
                },
                artist=intent.artist,
                title=intent.title,
                duration_s=intent.duration_s,
                source_system="legacy_identity_resolver",
                source_ref=intent.isrc or intent.beatport_id or intent.tidal_id,
            ),
            persist=True,
            allow_text_auto_match=False,
        )
        if result.decision != "accepted" or result.identity_id is None:
            return None
        try:
            row = self._conn.execute(
                """
                SELECT af.path
                FROM preferred_asset pa
                JOIN asset_file af ON af.id = pa.asset_id
                WHERE pa.identity_id = ?
                LIMIT 1
                """,
                (result.identity_id,),
            ).fetchone()
            if row is None:
                row = self._conn.execute(
                    """
                    SELECT af.path
                    FROM asset_link al
                    JOIN asset_file af ON af.id = al.asset_id
                    WHERE al.identity_id = ?
                    ORDER BY al.id ASC
                    LIMIT 1
                    """,
                    (result.identity_id,),
                ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        path = str(row[0])
        try:
            quality_row = self._conn.execute(
                "SELECT quality_rank FROM files WHERE path = ? LIMIT 1",
                (path,),
            ).fetchone()
        except sqlite3.OperationalError:
            quality_row = None
        quality_rank = int(quality_row[0]) if quality_row and quality_row[0] is not None else 0
        match_method = str(result.reasons.get("accepted_by") or "v3")
        return (path, quality_rank, match_method, result.confidence * 100.0)

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
