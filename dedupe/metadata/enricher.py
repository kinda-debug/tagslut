"""
Metadata enrichment orchestrator.

This module implements the main enrichment workflow:
1. Query eligible files from database (healthy, not yet enriched)
2. Extract local file info (tags, duration)
3. Run resolution state machine to identify tracks
4. Fetch metadata from providers
5. Apply cascade rules to select canonical values
6. Update database with results
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
from dataclasses import dataclass

from dedupe.metadata.models import (
    ProviderTrack,
    EnrichmentResult,
    LocalFileInfo,
    MatchConfidence,
    MetadataHealth,
    DURATION_PRECEDENCE,
    BPM_PRECEDENCE,
    KEY_PRECEDENCE,
    GENRE_PRECEDENCE,
)
from dedupe.metadata.auth import TokenManager
from dedupe.metadata.providers.base import (
    AbstractProvider,
    classify_match_confidence,
)
from dedupe.metadata.providers.spotify import SpotifyProvider
from dedupe.storage.schema import init_db

logger = logging.getLogger("dedupe.metadata.enricher")


@dataclass
class EnrichmentStats:
    """Statistics from an enrichment run."""
    total: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    no_match: int = 0


class Enricher:
    """
    Main enrichment orchestrator.

    Handles the complete enrichment workflow for eligible files.
    """

    def __init__(
        self,
        db_path: Path,
        token_manager: Optional[TokenManager] = None,
        providers: Optional[List[str]] = None,
        dry_run: bool = True,
    ):
        """
        Initialize the enricher.

        Args:
            db_path: Path to SQLite database
            token_manager: Token manager for API auth
            providers: List of provider names to use (default: ["spotify"])
            dry_run: If True, don't write to database
        """
        self.db_path = db_path
        self.token_manager = token_manager or TokenManager()
        self.provider_names = providers or ["spotify"]
        self.dry_run = dry_run

        # Initialize providers
        self._providers: Dict[str, AbstractProvider] = {}

    def _get_provider(self, name: str) -> Optional[AbstractProvider]:
        """Get or create a provider instance."""
        if name not in self._providers:
            if name == "spotify":
                self._providers[name] = SpotifyProvider(self.token_manager)
            elif name == "beatport":
                from dedupe.metadata.providers.beatport import BeatportProvider
                self._providers[name] = BeatportProvider(self.token_manager)
            elif name == "qobuz":
                from dedupe.metadata.providers.qobuz import QobuzProvider
                self._providers[name] = QobuzProvider(self.token_manager)
            elif name == "tidal":
                from dedupe.metadata.providers.tidal import TidalProvider
                self._providers[name] = TidalProvider(self.token_manager)
            elif name == "itunes":
                from dedupe.metadata.providers.itunes import iTunesProvider
                self._providers[name] = iTunesProvider()
            else:
                logger.warning("Unknown provider: %s", name)
                return None
        return self._providers.get(name)

    def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_eligible_files(
        self,
        path_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
    ) -> Iterator[LocalFileInfo]:
        """
        Query database for files eligible for enrichment.

        Eligible = healthy (flac_ok=1) AND not already enriched (unless force)

        Args:
            path_pattern: Optional SQL LIKE pattern to filter paths
            limit: Maximum files to return
            force: If True, include already-enriched files

        Yields:
            LocalFileInfo objects
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            query = """
                SELECT
                    path, duration, metadata_json,
                    enriched_at, canonical_isrc
                FROM files
                WHERE flac_ok = 1
            """
            params: List[Any] = []

            if not force:
                query += " AND enriched_at IS NULL"

            if path_pattern:
                query += " AND path LIKE ?"
                params.append(path_pattern)

            query += " ORDER BY path"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            cursor = conn.execute(query, params)

            for row in cursor:
                yield self._row_to_local_file_info(row)

        finally:
            conn.close()

    def _row_to_local_file_info(self, row: sqlite3.Row) -> LocalFileInfo:
        """Convert database row to LocalFileInfo."""
        # Parse metadata_json for tags
        metadata = {}
        if row["metadata_json"]:
            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                pass

        # Extract common tag fields
        # Tags from mutagen are often lists, take first element
        def get_tag(key: str) -> Optional[str]:
            val = metadata.get(key)
            if isinstance(val, list) and val:
                return str(val[0])
            elif val:
                return str(val)
            return None

        def get_int_tag(key: str) -> Optional[int]:
            val = get_tag(key)
            if val:
                try:
                    return int(val)
                except ValueError:
                    pass
            return None

        return LocalFileInfo(
            path=row["path"],
            measured_duration_s=row["duration"],
            tag_artist=get_tag("artist") or get_tag("albumartist"),
            tag_title=get_tag("title"),
            tag_album=get_tag("album"),
            tag_isrc=get_tag("isrc"),
            tag_label=get_tag("label") or get_tag("organization"),
            tag_year=get_int_tag("date") or get_int_tag("year"),
        )

    def resolve_file(self, file_info: LocalFileInfo) -> EnrichmentResult:
        """
        Run the resolution state machine for a single file.

        This implements the multi-stage resolution strategy from the guide:
        1. Try ISRC if available
        2. Try artist + title search
        3. Use duration to disambiguate

        Args:
            file_info: Local file information

        Returns:
            EnrichmentResult with matches and canonical values
        """
        result = EnrichmentResult(path=file_info.path)
        matches: List[ProviderTrack] = []

        def log(msg: str) -> None:
            result.log.append(msg)
            logger.debug("[%s] %s", file_info.path, msg)

        # Stage 1: Try ISRC if available
        if file_info.tag_isrc:
            log(f"Trying ISRC: {file_info.tag_isrc}")
            for provider_name in self.provider_names:
                provider = self._get_provider(provider_name)
                if provider is None:
                    continue

                isrc_matches = provider.search_by_isrc(file_info.tag_isrc)
                for m in isrc_matches:
                    m.match_confidence = MatchConfidence.EXACT
                    matches.append(m)
                    log(f"  {provider_name}: ISRC match -> {m.title} by {m.artist}")

        # Stage 2: Try artist + title search if no ISRC matches
        if not matches and file_info.tag_artist and file_info.tag_title:
            query = f"{file_info.tag_artist} {file_info.tag_title}"
            log(f"Trying text search: {query}")

            for provider_name in self.provider_names:
                provider = self._get_provider(provider_name)
                if provider is None:
                    continue

                search_results = provider.search(query, limit=5)
                for track in search_results:
                    # Score the match
                    confidence = classify_match_confidence(
                        file_info.tag_title,
                        file_info.tag_artist,
                        file_info.measured_duration_s,
                        track,
                    )
                    track.match_confidence = confidence

                    if confidence != MatchConfidence.NONE:
                        matches.append(track)
                        log(f"  {provider_name}: {confidence.value} match -> {track.title} by {track.artist}")

        # Stage 3: Title-only search as fallback
        if not matches and file_info.tag_title:
            log(f"Trying title-only search: {file_info.tag_title}")
            for provider_name in self.provider_names:
                provider = self._get_provider(provider_name)
                if provider is None:
                    continue

                search_results = provider.search(file_info.tag_title, limit=5)
                for track in search_results:
                    # More lenient scoring for title-only
                    confidence = classify_match_confidence(
                        file_info.tag_title,
                        None,  # No artist comparison
                        file_info.measured_duration_s,
                        track,
                        strong_duration_tolerance=5.0,
                        medium_duration_tolerance=15.0,
                    )
                    track.match_confidence = confidence

                    if confidence in (MatchConfidence.STRONG, MatchConfidence.MEDIUM):
                        matches.append(track)
                        log(f"  {provider_name}: {confidence.value} match -> {track.title} by {track.artist}")

        # Store all matches
        result.matches = matches

        # Apply cascade rules to get canonical values
        if matches:
            result = self._apply_cascade(result, file_info)
            result.enrichment_providers = list(set(m.service for m in matches))

            # Set overall confidence
            best_confidence = max(m.match_confidence for m in matches)
            result.enrichment_confidence = best_confidence
        else:
            log("No matches found")
            result.metadata_health = MetadataHealth.UNKNOWN
            result.metadata_health_reason = "no_provider_match"

        return result

    def _apply_cascade(
        self,
        result: EnrichmentResult,
        file_info: LocalFileInfo,
    ) -> EnrichmentResult:
        """
        Apply cascade rules to select canonical values from matches.

        Uses precedence lists to pick the best value for each field.
        """
        matches = result.matches
        if not matches:
            return result

        # Filter to usable matches (at least MEDIUM confidence)
        usable = [
            m for m in matches
            if m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG, MatchConfidence.MEDIUM)
        ]

        if not usable:
            usable = matches  # Fall back to all matches if none are high-confidence

        # Helper to pick value by precedence
        def pick_by_precedence(
            precedence: List[str],
            getter,
        ):
            for service in precedence:
                for m in usable:
                    if m.service == service:
                        val = getter(m)
                        if val is not None:
                            return val, service
            # Fallback: any value
            for m in usable:
                val = getter(m)
                if val is not None:
                    return val, m.service
            return None, None

        # Duration (for health check)
        duration, duration_source = pick_by_precedence(
            DURATION_PRECEDENCE,
            lambda m: m.duration_s,
        )
        if duration is not None:
            result.canonical_duration = duration
            result.canonical_duration_source = duration_source

            # Evaluate health
            if file_info.measured_duration_s is not None:
                result.metadata_health, result.metadata_health_reason = self._classify_health(
                    file_info.measured_duration_s,
                    duration,
                )

        # BPM
        bpm, _ = pick_by_precedence(BPM_PRECEDENCE, lambda m: m.bpm)
        result.canonical_bpm = bpm

        # Key
        key, _ = pick_by_precedence(KEY_PRECEDENCE, lambda m: m.key)
        result.canonical_key = key

        # Genre
        genre, _ = pick_by_precedence(GENRE_PRECEDENCE, lambda m: m.genre)
        result.canonical_genre = genre

        # ISRC (prefer exact from tags, then from providers)
        if file_info.tag_isrc:
            result.canonical_isrc = file_info.tag_isrc
        else:
            for m in usable:
                if m.isrc:
                    result.canonical_isrc = m.isrc
                    break

        # Label
        for m in usable:
            if m.label:
                result.canonical_label = m.label
                break

        # Year
        if file_info.tag_year:
            result.canonical_year = file_info.tag_year
        else:
            for m in usable:
                if m.year:
                    result.canonical_year = m.year
                    break

        return result

    def _classify_health(
        self,
        measured_duration: float,
        canonical_duration: float,
        tolerance: float = 2.0,
    ) -> tuple[MetadataHealth, str]:
        """
        Classify file health based on duration comparison.

        Args:
            measured_duration: Duration from local file (seconds)
            canonical_duration: Duration from provider (seconds)
            tolerance: Acceptable difference (seconds)

        Returns:
            (health_status, reason_string)
        """
        delta = measured_duration - canonical_duration

        if abs(delta) <= tolerance:
            return (
                MetadataHealth.OK,
                f"db={measured_duration:.3f}s, canonical={canonical_duration:.3f}s, delta={delta:.3f}s",
            )
        elif delta < 0:
            return (
                MetadataHealth.SUSPECT_TRUNCATED,
                f"db={measured_duration:.3f}s < canonical={canonical_duration:.3f}s (delta={delta:.3f}s)",
            )
        else:
            return (
                MetadataHealth.SUSPECT_EXTENDED,
                f"db={measured_duration:.3f}s > canonical={canonical_duration:.3f}s (delta={delta:.3f}s)",
            )

    def update_database(self, result: EnrichmentResult) -> bool:
        """
        Write enrichment result to database.

        Updates the files table with canonical values.

        Args:
            result: Enrichment result to write

        Returns:
            True if successful
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would update %s", result.path)
            return True

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE files SET
                    canonical_bpm = ?,
                    canonical_key = ?,
                    canonical_genre = ?,
                    canonical_isrc = ?,
                    canonical_label = ?,
                    canonical_year = ?,
                    canonical_duration = ?,
                    canonical_duration_source = ?,
                    metadata_health = ?,
                    metadata_health_reason = ?,
                    enriched_at = ?,
                    enrichment_providers = ?,
                    enrichment_confidence = ?
                WHERE path = ?
                """,
                (
                    result.canonical_bpm,
                    result.canonical_key,
                    result.canonical_genre,
                    result.canonical_isrc,
                    result.canonical_label,
                    result.canonical_year,
                    result.canonical_duration,
                    result.canonical_duration_source,
                    result.metadata_health.value if result.metadata_health else None,
                    result.metadata_health_reason,
                    datetime.utcnow().isoformat(),
                    json.dumps(result.enrichment_providers) if result.enrichment_providers else None,
                    result.enrichment_confidence.value if result.enrichment_confidence else None,
                    result.path,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error("Database update failed: %s", e)
            return False
        finally:
            conn.close()

    def enrich_all(
        self,
        path_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
        progress_callback=None,
    ) -> EnrichmentStats:
        """
        Enrich all eligible files.

        Args:
            path_pattern: Optional SQL LIKE pattern to filter paths
            limit: Maximum files to process
            force: If True, re-enrich already-enriched files
            progress_callback: Optional callback(current, total, path) for progress

        Returns:
            EnrichmentStats with counts
        """
        stats = EnrichmentStats()

        # Get all eligible files
        files = list(self.get_eligible_files(path_pattern, limit, force))
        stats.total = len(files)

        if stats.total == 0:
            logger.info("No eligible files found")
            return stats

        logger.info("Processing %d files", stats.total)

        for i, file_info in enumerate(files):
            if progress_callback:
                progress_callback(i + 1, stats.total, file_info.path)

            try:
                # Resolve and enrich
                result = self.resolve_file(file_info)

                if not result.matches:
                    stats.no_match += 1
                    continue

                # Update database
                if self.update_database(result):
                    stats.enriched += 1
                else:
                    stats.failed += 1

            except Exception as e:
                logger.error("Failed to enrich %s: %s", file_info.path, e)
                stats.failed += 1

        return stats
