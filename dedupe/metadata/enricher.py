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
    SUB_GENRE_PRECEDENCE,
    LABEL_PRECEDENCE,
    CATALOG_NUMBER_PRECEDENCE,
    TITLE_PRECEDENCE,
    ARTIST_PRECEDENCE,
    ALBUM_PRECEDENCE,
    ARTWORK_PRECEDENCE,
    AUDIO_FEATURES_SOURCE,
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
    no_match_files: List[str] = None  # Paths of files with no match

    def __post_init__(self):
        if self.no_match_files is None:
            self.no_match_files = []


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
        mode: str = "recovery",
    ):
        """
        Initialize the enricher.

        Args:
            db_path: Path to SQLite database
            token_manager: Token manager for API auth
            providers: List of provider names to use (default: ["spotify"])
            dry_run: If True, don't write to database
            mode: Operation mode - "recovery", "hoarding", or "both"
                  - recovery: Focus on duration health validation, accept lower-confidence matches
                  - hoarding: Focus on full metadata, require high-confidence matches
                  - both: Do both recovery and hoarding
        """
        self.db_path = db_path
        self.token_manager = token_manager or TokenManager()
        self.provider_names = providers or ["spotify"]
        self.dry_run = dry_run
        self.mode = mode

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
        retry_no_match: bool = False,
    ) -> Iterator[LocalFileInfo]:
        """
        Query database for files eligible for enrichment.

        Eligible = healthy (flac_ok=1) AND not already enriched (unless force/retry)

        Args:
            path_pattern: Optional SQL LIKE pattern to filter paths
            limit: Maximum files to return
            force: If True, include ALL already-enriched files
            retry_no_match: If True, include files that previously had no match

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

            if force:
                # Re-process everything
                pass
            elif retry_no_match:
                # Only retry files that had no match
                query += " AND (enriched_at IS NULL OR metadata_health_reason = 'no_provider_match')"
            else:
                # Skip all processed files
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

        # Enrich Spotify matches with audio features (BPM, key, energy, etc.)
        if self.mode in ("hoarding", "both"):
            spotify_provider = self._get_provider("spotify")
            if spotify_provider and hasattr(spotify_provider, 'enrich_with_audio_features'):
                for m in matches:
                    if m.service == "spotify" and m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG):
                        spotify_provider.enrich_with_audio_features(m)
                        log(f"  spotify: enriched with audio features (BPM={m.bpm}, key={m.key})")

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

        Behavior varies by mode:
        - recovery: Accept lower-confidence matches for duration/health
        - hoarding: Require high-confidence matches for full metadata
        - both: Apply both strategies

        Uses precedence lists to pick the best value for each field.
        """
        matches = result.matches
        if not matches:
            return result

        # For RECOVERY: accept medium/weak matches for duration
        recovery_usable = [
            m for m in matches
            if m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG, MatchConfidence.MEDIUM, MatchConfidence.WEAK)
        ]

        # For HOARDING: require high-confidence matches
        hoarding_usable = [
            m for m in matches
            if m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG)
        ]

        # Helper to pick value by precedence
        def pick_by_precedence(
            precedence: List[str],
            getter,
            usable_matches: List[ProviderTrack],
        ):
            for service in precedence:
                for m in usable_matches:
                    if m.service == service:
                        val = getter(m)
                        if val is not None:
                            return val, service
            # Fallback: any value from usable
            for m in usable_matches:
                val = getter(m)
                if val is not None:
                    return val, m.service
            return None, None

        # RECOVERY MODE: Duration and health (accept lower-confidence)
        if self.mode in ("recovery", "both"):
            duration, duration_source = pick_by_precedence(
                DURATION_PRECEDENCE,
                lambda m: m.duration_s,
                recovery_usable,
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

        # HOARDING MODE: Full metadata (require high-confidence)
        if self.mode in ("hoarding", "both"):
            if not hoarding_usable:
                # No high-confidence matches - skip hoarding fields
                logger.debug("No high-confidence matches for hoarding mode")
            else:
                # Core identity
                title, _ = pick_by_precedence(TITLE_PRECEDENCE, lambda m: m.title, hoarding_usable)
                result.canonical_title = title

                artist, _ = pick_by_precedence(ARTIST_PRECEDENCE, lambda m: m.artist, hoarding_usable)
                result.canonical_artist = artist

                album, _ = pick_by_precedence(ALBUM_PRECEDENCE, lambda m: m.album, hoarding_usable)
                result.canonical_album = album

                # ISRC (prefer exact from tags, then from providers)
                if file_info.tag_isrc:
                    result.canonical_isrc = file_info.tag_isrc
                else:
                    for m in hoarding_usable:
                        if m.isrc:
                            result.canonical_isrc = m.isrc
                            break

                # DJ metadata
                bpm, _ = pick_by_precedence(BPM_PRECEDENCE, lambda m: m.bpm, hoarding_usable)
                result.canonical_bpm = bpm

                key, _ = pick_by_precedence(KEY_PRECEDENCE, lambda m: m.key, hoarding_usable)
                result.canonical_key = key

                genre, _ = pick_by_precedence(GENRE_PRECEDENCE, lambda m: m.genre, hoarding_usable)
                result.canonical_genre = genre

                sub_genre, _ = pick_by_precedence(SUB_GENRE_PRECEDENCE, lambda m: m.sub_genre, hoarding_usable)
                result.canonical_sub_genre = sub_genre

                # Release info
                label, _ = pick_by_precedence(LABEL_PRECEDENCE, lambda m: m.label, hoarding_usable)
                result.canonical_label = label

                catalog_num, _ = pick_by_precedence(CATALOG_NUMBER_PRECEDENCE, lambda m: m.catalog_number, hoarding_usable)
                result.canonical_catalog_number = catalog_num

                # Mix name (Beatport)
                for m in hoarding_usable:
                    if m.mix_name:
                        result.canonical_mix_name = m.mix_name
                        break

                # Year / release date
                if file_info.tag_year:
                    result.canonical_year = file_info.tag_year
                else:
                    for m in hoarding_usable:
                        if m.year:
                            result.canonical_year = m.year
                            break
                for m in hoarding_usable:
                    if m.release_date:
                        result.canonical_release_date = m.release_date
                        break

                # Explicit flag
                for m in hoarding_usable:
                    if m.explicit is not None:
                        result.canonical_explicit = m.explicit
                        break

                # Artwork
                artwork, _ = pick_by_precedence(ARTWORK_PRECEDENCE, lambda m: m.album_art_url, hoarding_usable)
                result.canonical_album_art_url = artwork

                # Spotify audio features (only from Spotify)
                spotify_match = next((m for m in hoarding_usable if m.service == AUDIO_FEATURES_SOURCE), None)
                if spotify_match:
                    result.canonical_energy = spotify_match.energy
                    result.canonical_danceability = spotify_match.danceability
                    result.canonical_valence = spotify_match.valence
                    result.canonical_acousticness = spotify_match.acousticness
                    result.canonical_instrumentalness = spotify_match.instrumentalness
                    result.canonical_loudness = spotify_match.loudness

                # Provider IDs for linking
                for m in hoarding_usable:
                    if m.service == "spotify" and m.service_track_id:
                        result.spotify_id = m.service_track_id
                    elif m.service == "beatport" and m.service_track_id:
                        result.beatport_id = m.service_track_id
                    elif m.service == "tidal" and m.service_track_id:
                        result.tidal_id = m.service_track_id
                    elif m.service == "qobuz" and m.service_track_id:
                        result.qobuz_id = m.service_track_id
                    elif m.service == "itunes" and m.service_track_id:
                        result.itunes_id = m.service_track_id

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

        Updates the files table with canonical values based on mode:
        - recovery: Only writes duration and health fields
        - hoarding: Only writes BPM, key, genre, etc.
        - both: Writes all fields

        Args:
            result: Enrichment result to write

        Returns:
            True if successful
        """
        if self.dry_run:
            logger.info("[DRY-RUN] Would update %s (mode=%s)", result.path, self.mode)
            return True

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Build dynamic UPDATE based on mode
            fields = []
            values = []

            # Always write enriched_at, providers, and confidence
            fields.extend(["enriched_at = ?", "enrichment_providers = ?", "enrichment_confidence = ?"])
            values.extend([
                datetime.utcnow().isoformat(),
                json.dumps(result.enrichment_providers) if result.enrichment_providers else None,
                result.enrichment_confidence.value if result.enrichment_confidence else None,
            ])

            # RECOVERY fields: duration and health
            if self.mode in ("recovery", "both"):
                fields.extend([
                    "canonical_duration = ?",
                    "canonical_duration_source = ?",
                    "metadata_health = ?",
                    "metadata_health_reason = ?",
                ])
                values.extend([
                    result.canonical_duration,
                    result.canonical_duration_source,
                    result.metadata_health.value if result.metadata_health else None,
                    result.metadata_health_reason,
                ])

            # HOARDING fields: full metadata
            if self.mode in ("hoarding", "both"):
                fields.extend([
                    # Core identity
                    "canonical_title = ?",
                    "canonical_artist = ?",
                    "canonical_album = ?",
                    "canonical_isrc = ?",
                    # DJ metadata
                    "canonical_bpm = ?",
                    "canonical_key = ?",
                    "canonical_genre = ?",
                    "canonical_sub_genre = ?",
                    # Release info
                    "canonical_label = ?",
                    "canonical_catalog_number = ?",
                    "canonical_mix_name = ?",
                    "canonical_year = ?",
                    "canonical_release_date = ?",
                    "canonical_explicit = ?",
                    # Spotify audio features
                    "canonical_energy = ?",
                    "canonical_danceability = ?",
                    "canonical_valence = ?",
                    "canonical_acousticness = ?",
                    "canonical_instrumentalness = ?",
                    "canonical_loudness = ?",
                    # Artwork
                    "canonical_album_art_url = ?",
                    # Provider IDs
                    "spotify_id = ?",
                    "beatport_id = ?",
                    "tidal_id = ?",
                    "qobuz_id = ?",
                    "itunes_id = ?",
                ])
                values.extend([
                    # Core identity
                    result.canonical_title,
                    result.canonical_artist,
                    result.canonical_album,
                    result.canonical_isrc,
                    # DJ metadata
                    result.canonical_bpm,
                    result.canonical_key,
                    result.canonical_genre,
                    result.canonical_sub_genre,
                    # Release info
                    result.canonical_label,
                    result.canonical_catalog_number,
                    result.canonical_mix_name,
                    result.canonical_year,
                    result.canonical_release_date,
                    1 if result.canonical_explicit else (0 if result.canonical_explicit is False else None),
                    # Spotify audio features
                    result.canonical_energy,
                    result.canonical_danceability,
                    result.canonical_valence,
                    result.canonical_acousticness,
                    result.canonical_instrumentalness,
                    result.canonical_loudness,
                    # Artwork
                    result.canonical_album_art_url,
                    # Provider IDs
                    result.spotify_id,
                    result.beatport_id,
                    result.tidal_id,
                    result.qobuz_id,
                    result.itunes_id,
                ])

            # Add path for WHERE clause
            values.append(result.path)

            query = f"UPDATE files SET {', '.join(fields)} WHERE path = ?"
            cursor.execute(query, values)
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
        retry_no_match: bool = False,
        progress_callback=None,
        checkpoint_interval: int = 50,
    ) -> EnrichmentStats:
        """
        Enrich all eligible files.

        Resumable: Files are marked when processed (enriched or no_match),
        so interrupted runs can be resumed without re-processing.

        Args:
            path_pattern: Optional SQL LIKE pattern to filter paths
            limit: Maximum files to process
            force: If True, re-enrich ALL already-enriched files
            retry_no_match: If True, retry files that previously had no match
            progress_callback: Optional callback(current, total, path) for progress
            checkpoint_interval: Log progress every N files

        Returns:
            EnrichmentStats with counts
        """
        stats = EnrichmentStats()

        # Get all eligible files
        files = list(self.get_eligible_files(path_pattern, limit, force, retry_no_match))
        stats.total = len(files)

        if stats.total == 0:
            logger.info("No eligible files found")
            return stats

        logger.debug("Processing %d files", stats.total)

        try:
            for i, file_info in enumerate(files):
                if progress_callback:
                    progress_callback(i + 1, stats.total, file_info.path)

                # Checkpoint logging (quieter - only to log file)
                if (i + 1) % checkpoint_interval == 0:
                    logger.debug(
                        "Checkpoint %d/%d: enriched=%d, no_match=%d, failed=%d",
                        i + 1, stats.total, stats.enriched, stats.no_match, stats.failed
                    )

                try:
                    # Resolve and enrich
                    result = self.resolve_file(file_info)

                    if not result.matches:
                        stats.no_match += 1
                        stats.no_match_files.append(file_info.path)
                        # Mark as processed with no_match so we don't retry
                        self._mark_no_match(file_info.path)
                        logger.info("NO MATCH: %s (searched: %s %s)",
                            file_info.path,
                            file_info.tag_artist or "?",
                            file_info.tag_title or "?")
                        continue

                    # Update database
                    if self.update_database(result):
                        stats.enriched += 1
                        # Log match details
                        best_match = max(result.matches, key=lambda m: m.match_confidence.value if m.match_confidence else 0)
                        logger.info("MATCH: %s -> %s - %s [%s] (%s)",
                            file_info.path,
                            best_match.artist,
                            best_match.title,
                            best_match.service,
                            result.enrichment_confidence.value if result.enrichment_confidence else "?")
                    else:
                        stats.failed += 1
                        logger.warning("FAILED to update: %s", file_info.path)

                except KeyboardInterrupt:
                    raise  # Re-raise to outer handler
                except Exception as e:
                    logger.warning("Error processing %s: %s", file_info.path, e)
                    stats.failed += 1
                    # Continue to next file instead of stopping

        except KeyboardInterrupt:
            stats.total = i + 1  # Adjust total to reflect actual processed
            logger.debug("Interrupted at file %d", i + 1)

        logger.debug(
            "Done: enriched=%d, no_match=%d, failed=%d",
            stats.enriched, stats.no_match, stats.failed
        )

        return stats

    def _mark_no_match(self, path: str) -> None:
        """Mark a file as processed but with no provider match."""
        if self.dry_run:
            return

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """UPDATE files SET
                    enriched_at = ?,
                    metadata_health = 'unknown',
                    metadata_health_reason = 'no_provider_match'
                WHERE path = ?""",
                (datetime.utcnow().isoformat(), path)
            )
            conn.commit()
        except sqlite3.Error as e:
            logger.debug("Failed to mark no_match for %s: %s", path, e)
        finally:
            conn.close()
