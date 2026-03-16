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

import csv
from dataclasses import asdict
import logging
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Dict, Iterator, List, Optional, cast

from tagslut.metadata.models import (
    TIDAL_BEATPORT_MERGED_COLUMNS,
    TIDAL_SEED_COLUMNS,
    TidalBeatportMergedRow,
    TidalSeedRow,
)
from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.base import AbstractProvider as BaseProvider
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
        self._providers: Dict[str, BaseProvider] = {}

    def _get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get or create a provider instance."""
        if name not in self._providers:
            if name == "spotify":
                logger.warning("Spotify provider is disabled by policy (API changes).")
                return None
            elif name == "beatport":
                from tagslut.metadata.providers.beatport import BeatportProvider
                self._providers[name] = cast(
                    BaseProvider,
                    cast(Any, BeatportProvider)(self.token_manager),
                )
            elif name == "qobuz":
                logger.warning("Qobuz provider is disabled by policy.")
                return None
            elif name == "deezer":
                from tagslut.metadata.providers.deezer import DeezerProvider
                self._providers[name] = cast(
                    BaseProvider,
                    cast(Any, DeezerProvider)(),
                )
            elif name == "tidal":
                from tagslut.metadata.providers.tidal import TidalProvider
                self._providers[name] = TidalProvider(self.token_manager)
            elif name == "itunes":
                logger.warning("iTunes provider is disabled by policy (use Apple Music via MusicBrainz).")
                return None
            elif name == "apple_music":
                from tagslut.metadata.providers.apple_music import AppleMusicProvider
                self._providers[name] = AppleMusicProvider(self.token_manager)
            elif name == "musicbrainz":
                from tagslut.metadata.providers.musicbrainz import MusicBrainzProvider
                self._providers[name] = MusicBrainzProvider()
            elif name == "traxsource":
                from tagslut.metadata.providers.traxsource import TraxsourceProvider
                self._providers[name] = TraxsourceProvider()
            else:
                logger.warning("Unknown provider: %s", name)
                return None
        return self._providers.get(name)

    def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()

    def __enter__(self) -> "Enricher":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    @staticmethod
    def _optional_csv_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _load_tidal_seed_rows(input_csv: Path) -> List[TidalSeedRow]:
        rows: List[TidalSeedRow] = []
        with input_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                tidal_playlist_id = (raw.get("tidal_playlist_id") or "").strip()
                tidal_track_id = (raw.get("tidal_track_id") or "").strip()
                tidal_url = (raw.get("tidal_url") or "").strip()
                title = (raw.get("title") or "").strip()
                artist = (raw.get("artist") or "").strip()
                if not tidal_playlist_id or not tidal_track_id or not tidal_url or not title or not artist:
                    logger.debug("Skipping incomplete TIDAL seed row: %s", raw)
                    continue
                rows.append(
                    TidalSeedRow(
                        tidal_playlist_id=tidal_playlist_id,
                        tidal_track_id=tidal_track_id,
                        tidal_url=tidal_url,
                        title=title,
                        artist=artist,
                        isrc=Enricher._optional_csv_value(raw.get("isrc")),
                    )
                )
        return rows

    @staticmethod
    def _write_csv_rows(output_csv: Path, fieldnames: tuple[str, ...], rows: List[dict[str, Any]]) -> None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

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

    def export_tidal_seed_csv(self, playlist_url: str, output_csv: Path) -> None:
        """Export one stable TIDAL playlist seed CSV."""
        provider = self._get_provider("tidal")
        if provider is None or not hasattr(provider, "export_playlist_seed_rows"):
            raise RuntimeError("TIDAL provider is unavailable for playlist seed export")

        seed_rows = cast(List[TidalSeedRow], provider.export_playlist_seed_rows(playlist_url))
        self._write_csv_rows(output_csv, TIDAL_SEED_COLUMNS, [asdict(row) for row in seed_rows])

        playlist_id = seed_rows[0].tidal_playlist_id if seed_rows else playlist_url
        missing_isrc = sum(1 for row in seed_rows if not row.isrc)
        logger.info(
            "TIDAL seed export complete: playlist_id=%s total_tracks=%d rows_missing_isrc=%d output=%s",
            playlist_id,
            len(seed_rows),
            missing_isrc,
            output_csv,
        )

    def enrich_tidal_seed_csv(self, input_csv: Path, output_csv: Path) -> None:
        """Enrich a TIDAL seed CSV row-by-row using Beatport-only lookup."""
        provider = self._get_provider("beatport")
        if provider is None or not hasattr(provider, "enrich_tidal_seed_row"):
            raise RuntimeError("Beatport provider is unavailable for seed enrichment")

        seed_rows = self._load_tidal_seed_rows(input_csv)
        merged_rows = [
            cast(TidalBeatportMergedRow, provider.enrich_tidal_seed_row(seed_row))
            for seed_row in seed_rows
        ]
        self._write_csv_rows(output_csv, TIDAL_BEATPORT_MERGED_COLUMNS, [asdict(row) for row in merged_rows])

        logger.info(
            "Beatport enrichment complete: total_rows=%d matched_isrc=%d matched_fallback=%d unmatched=%d output=%s",
            len(merged_rows),
            sum(1 for row in merged_rows if row.match_method == "isrc"),
            sum(1 for row in merged_rows if row.match_method == "title_artist_fallback"),
            sum(1 for row in merged_rows if row.match_method == "no_match"),
            output_csv,
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

    def enrich_all(
        self,
        path_pattern: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
        retry_no_match: bool = False,
        zones: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
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
