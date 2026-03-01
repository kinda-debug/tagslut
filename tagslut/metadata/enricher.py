"""
Metadata enrichment orchestrator.

This module implements the main enrichment workflow:
1. Query eligible files from database (healthy, not yet enriched)
2. Extract local file info (tags, duration)
3. Run resolution state machine to identify tracks
4. Fetch metadata from providers
5. Apply cascade rules to select canonical metadata values
6. Update database with results
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Iterator

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.base import AbstractProvider
from tagslut.metadata.pipeline import runner, stages
from tagslut.metadata.store import db_reader, db_writer

logger = logging.getLogger("tagslut.metadata.enricher")

# Re-export for compatibility
EnrichmentStats = runner.EnrichmentStats


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
            providers: List of provider names to use (default: ["beatport"])
            dry_run: If True, don't write to database
            mode: Operation mode - "recovery", "hoarding", or "both"
                  - recovery: Focus on duration health validation, accept lower-confidence matches
                  - hoarding: Focus on full metadata, require high-confidence matches
                  - both: Do both recovery and hoarding
        """
        self.db_path = db_path
        self.token_manager = token_manager or TokenManager()
        self.provider_names = providers or ["beatport"]
        self.dry_run = dry_run
        self.mode = mode

        # Initialize providers
        self._providers: Dict[str, AbstractProvider] = {}

    def _get_provider(self, name: str) -> Optional[AbstractProvider]:
        """Get or create a provider instance."""
        if name not in self._providers:
            if name == "spotify":
                logger.warning("Spotify provider is disabled by policy (API changes).")
                return None
            elif name == "beatport":
                from tagslut.metadata.providers.beatport import BeatportProvider
                self._providers[name] = BeatportProvider(self.token_manager)  # type: ignore  # TODO: mypy-strict
            elif name == "qobuz":
                logger.warning("Qobuz provider is disabled by policy.")
                return None
            elif name == "deezer":
                from tagslut.metadata.providers.deezer import DeezerProvider
                self._providers[name] = DeezerProvider()  # type: ignore  # TODO: mypy-strict
            elif name == "tidal":
                from tagslut.metadata.providers.tidal import TidalProvider
                self._providers[name] = TidalProvider(self.token_manager)
            elif name == "itunes":
                from tagslut.metadata.providers.itunes import iTunesProvider
                self._providers[name] = iTunesProvider()  # type: ignore  # TODO: mypy-strict
            elif name == "apple_music":
                from tagslut.metadata.providers.apple_music import AppleMusicProvider
                self._providers[name] = AppleMusicProvider(self.token_manager)  # type: ignore  # TODO: mypy-strict
            elif name == "musicbrainz":
                from tagslut.metadata.providers.musicbrainz import MusicBrainzProvider
                self._providers[name] = MusicBrainzProvider()
            elif name == "traxsource":
                from tagslut.metadata.providers.traxsource import TraxsourceProvider
                self._providers[name] = TraxsourceProvider()  # type: ignore  # TODO: mypy-strict
            else:
                logger.warning("Unknown provider: %s", name)
                return None
        return self._providers.get(name)

    def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()

    def __enter__(self):  # type: ignore  # TODO: mypy-strict
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):  # type: ignore  # TODO: mypy-strict
        self.close()

    def get_eligible_files(
        self,
        path_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
        retry_no_match: bool = False,
        zones: Optional[List[str]] = None,
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
        return db_reader.get_eligible_files(
            self.db_path,
            path_pattern=path_pattern,
            limit=limit,
            force=force,
            retry_no_match=retry_no_match,
            zones=zones,
        )

    def get_file_info(self, path: str) -> Optional[LocalFileInfo]:
        """Fetch a single file by path."""
        return db_reader.get_file_info(self.db_path, path)

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
        return stages.resolve_file(
            file_info,
            self.provider_names,
            self._get_provider,
            self.mode,
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
        return db_writer.update_database(self.db_path, result, self.dry_run, self.mode)

    def _mark_no_match(self, path: str) -> None:
        """Mark a file as processed but with no provider match."""
        db_writer.mark_no_match(self.db_path, path, self.dry_run)

    def enrich_all(  # type: ignore  # TODO: mypy-strict
        self,
        path_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
        retry_no_match: bool = False,
        zones: Optional[List[str]] = None,
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
        return runner.run_enrich_all(
            self.db_path,
            self.provider_names,
            self._get_provider,
            self.mode,
            self.dry_run,
            path_pattern=path_pattern,
            limit=limit,
            force=force,
            retry_no_match=retry_no_match,
            zones=zones,
            progress_callback=progress_callback,
            checkpoint_interval=checkpoint_interval,
        )

    def enrich_file(
        self,
        path: str,
        *,
        force: bool = False,
        retry_no_match: bool = False,
    ) -> tuple[Optional[EnrichmentResult], str]:
        """
        Enrich a single file by exact path.

        Returns (result, status) where status is one of:
        - enriched, no_match, failed, not_found, not_eligible, not_flac_ok
        """
        return runner.run_enrich_file(
            self.db_path,
            self.provider_names,
            self._get_provider,
            self.mode,
            self.dry_run,
            path,
            force=force,
            retry_no_match=retry_no_match,
        )
