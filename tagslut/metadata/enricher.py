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
from typing import Any, Dict, Iterator, List, Optional, cast

from tagslut.metadata.models.types import (
    BEATPORT_SEED_COLUMNS,
    BEATPORT_TIDAL_MERGED_COLUMNS,
    BeatportSeedExportStats,
    BeatportSeedRow,
    BeatportTidalEnrichmentStats,
    BeatportTidalMergedRow,
    CONFIDENCE_NUMERIC,
    MatchConfidence,
    TIDAL_BEATPORT_MERGED_COLUMNS,
    TIDAL_SEED_COLUMNS,
    TidalBeatportEnrichmentStats,
    TidalBeatportMergedRow,
    TidalSeedExportStats,
    TidalSeedRow,
    EnrichmentResult,
    LocalFileInfo,
)
from tagslut.metadata.auth import TokenManager
from tagslut.metadata.providers.base import AbstractProvider as BaseProvider
from tagslut.metadata.capabilities import Capability
from tagslut.metadata.provider_registry import (
    DEFAULT_ACTIVE_PROVIDERS,
    get_provider_class,
    load_provider_activation_config,
    resolve_active_metadata_providers,
)
from tagslut.metadata.metadata_router import MetadataRouter
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
        providers_config_path: Optional[Path] = None,
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
        activation = load_provider_activation_config(providers_config_path)
        self.provider_activation = activation
        requested = providers or DEFAULT_ACTIVE_PROVIDERS
        self.provider_names = resolve_active_metadata_providers(requested, config=activation)
        self.dry_run = dry_run
        self.mode = mode
        self.router = MetadataRouter(
            provider_names=self.provider_names,
            activation=self.provider_activation,
            token_manager=self.token_manager,
        )

        # Initialize providers
        self._providers: Dict[str, BaseProvider] = {}

    def _get_provider(self, name: str) -> Optional[BaseProvider]:
        """Get or create a provider instance using the ProviderRegistry."""
        if name not in self._providers:
            try:
                provider_cls = get_provider_class(name)
                self._providers[name] = provider_cls(self.token_manager)
            except Exception as e:
                logger.warning("Unknown or failed provider '%s': %s", name, e)
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
    def _load_tidal_seed_rows(input_csv: Path) -> tuple[List[TidalSeedRow], int, int]:
        rows: List[TidalSeedRow] = []
        input_rows = 0
        discarded_rows = 0
        with input_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                input_rows += 1
                tidal_playlist_id = (raw.get("tidal_playlist_id") or "").strip()
                tidal_track_id = (raw.get("tidal_track_id") or "").strip()
                tidal_url = (raw.get("tidal_url") or "").strip()
                title = (raw.get("title") or "").strip()
                artist = (raw.get("artist") or "").strip()
                if not tidal_playlist_id or not tidal_track_id or not tidal_url or not title or not artist:
                    logger.debug("Skipping incomplete TIDAL seed row: %s", raw)
                    discarded_rows += 1
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
        return rows, input_rows, discarded_rows

    @staticmethod
    def _load_beatport_seed_rows(input_csv: Path) -> tuple[List[BeatportSeedRow], int, int]:
        rows: List[BeatportSeedRow] = []
        input_rows = 0
        discarded_rows = 0
        with input_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                input_rows += 1
                beatport_track_id = (raw.get("beatport_track_id") or "").strip()
                beatport_url = (raw.get("beatport_url") or "").strip()
                title = (raw.get("title") or "").strip()
                artist = (raw.get("artist") or "").strip()
                if not beatport_track_id or not beatport_url or not title or not artist:
                    logger.debug("Skipping incomplete Beatport seed row: %s", raw)
                    discarded_rows += 1
                    continue
                rows.append(
                    BeatportSeedRow(
                        beatport_track_id=beatport_track_id,
                        beatport_release_id=Enricher._optional_csv_value(raw.get("beatport_release_id")),
                        beatport_url=beatport_url,
                        title=title,
                        artist=artist,
                        isrc=Enricher._optional_csv_value(raw.get("isrc")),
                        beatport_bpm=Enricher._optional_csv_value(raw.get("beatport_bpm")),
                        beatport_key=Enricher._optional_csv_value(raw.get("beatport_key")),
                        beatport_genre=Enricher._optional_csv_value(raw.get("beatport_genre")),
                        beatport_subgenre=Enricher._optional_csv_value(raw.get("beatport_subgenre")),
                        beatport_label=Enricher._optional_csv_value(raw.get("beatport_label")),
                        beatport_catalog_number=Enricher._optional_csv_value(raw.get("beatport_catalog_number")),
                        beatport_upc=Enricher._optional_csv_value(raw.get("beatport_upc")),
                        beatport_release_date=Enricher._optional_csv_value(raw.get("beatport_release_date")),
                    )
                )
        return rows, input_rows, discarded_rows

    @staticmethod
    def _write_csv_rows(output_csv: Path, fieldnames: tuple[str, ...], rows: List[dict[str, Any]]) -> None:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with output_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
            writer.writeheader()
            for row in rows:
                # Serialize match_confidence enum to float for CSV output
                if "match_confidence" in row and isinstance(row["match_confidence"], MatchConfidence):
                    row = dict(row)
                    row["match_confidence"] = CONFIDENCE_NUMERIC[row["match_confidence"]]
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

    def export_tidal_seed_csv(self, playlist_url: str, output_csv: Path) -> TidalSeedExportStats:
        """Export one stable TIDAL playlist seed CSV."""
        if "tidal" not in self.router.provider_names_for(Capability.METADATA_EXPORT_PLAYLIST_SEED):
            raise RuntimeError("TIDAL playlist seed export unavailable (provider disabled or unauthenticated)")
        provider = self._get_provider("tidal")
        if provider is None or not hasattr(provider, "export_playlist_seed_rows"):
            raise RuntimeError("TIDAL provider is unavailable for playlist seed export")

        seed_rows, stats = cast(
            tuple[List[TidalSeedRow], TidalSeedExportStats],
            provider.export_playlist_seed_rows(playlist_url),
        )
        self._write_csv_rows(output_csv, TIDAL_SEED_COLUMNS, [asdict(row) for row in seed_rows])

        logger.info(
            "TIDAL seed export complete: playlist_id=%s exported=%d missing_isrc=%d malformed=%d missing_required=%d duplicates=%d pages=%d fallback=%d stop_non_200=%d stop_empty=%d stop_repeated_next=%d stop_short_no_next=%d output=%s",
            stats.playlist_id,
            stats.exported_rows,
            stats.missing_isrc_rows,
            stats.malformed_playlist_items,
            stats.rows_missing_required_fields,
            stats.duplicate_rows,
            stats.pages_fetched,
            stats.endpoint_fallback_used,
            stats.pagination_stop_non_200,
            stats.pagination_stop_empty_page,
            stats.pagination_stop_repeated_next,
            stats.pagination_stop_short_page_no_next,
            output_csv,
        )
        return stats

    def export_beatport_seed_csv(self, output_csv: Path) -> BeatportSeedExportStats:
        """Export one stable Beatport library seed CSV."""
        provider = self._get_provider("beatport")
        if provider is None or not hasattr(provider, "export_my_tracks_seed_rows"):
            raise RuntimeError("Beatport provider is unavailable for library seed export")

        seed_rows, stats = cast(
            tuple[List[BeatportSeedRow], BeatportSeedExportStats],
            provider.export_my_tracks_seed_rows(),
        )
        self._write_csv_rows(output_csv, BEATPORT_SEED_COLUMNS, [asdict(row) for row in seed_rows])

        logger.info(
            "Beatport seed export complete: exported=%d missing_isrc=%d missing_required=%d duplicates=%d pages=%d stop_non_200=%d stop_empty=%d stop_short_no_next=%d output=%s",
            stats.exported_rows,
            stats.missing_isrc_rows,
            stats.rows_missing_required_fields,
            stats.duplicate_rows,
            stats.pages_fetched,
            stats.pagination_stop_non_200,
            stats.pagination_stop_empty_page,
            stats.pagination_stop_short_page_no_next,
            output_csv,
        )
        return stats

    def enrich_tidal_seed_csv(
        self,
        input_csv: Path,
        output_csv: Path,
    ) -> TidalBeatportEnrichmentStats:
        """Enrich a TIDAL seed CSV row-by-row using Beatport-only lookup."""
        provider = self._get_provider("beatport")
        if provider is None or not hasattr(provider, "enrich_tidal_seed_row"):
            raise RuntimeError("Beatport provider is unavailable for seed enrichment")

        seed_rows, input_rows, discarded_rows = self._load_tidal_seed_rows(input_csv)
        stats = TidalBeatportEnrichmentStats(
            input_rows=input_rows,
            discarded_seed_rows=discarded_rows,
        )
        merged_rows: List[TidalBeatportMergedRow] = []
        for seed_row in seed_rows:
            merged_row, telemetry = cast(
                tuple[TidalBeatportMergedRow, Dict[str, int]],
                provider.enrich_tidal_seed_row(seed_row),
            )
            merged_rows.append(merged_row)
            stats.output_rows += 1
            stats.ambiguous_isrc_rows += telemetry.get("ambiguous_isrc_rows", 0)
            stats.ambiguous_fallback_rows += telemetry.get("ambiguous_fallback_rows", 0)
            stats.fallback_equal_rank_ties += telemetry.get("fallback_equal_rank_ties", 0)
            if merged_row.match_method == "isrc":
                stats.isrc_matches += 1
            elif merged_row.match_method == "title_artist_fallback":
                stats.title_artist_fallback_matches += 1
            elif merged_row.match_method == "no_match":
                stats.no_match_rows += 1

        self._write_csv_rows(output_csv, TIDAL_BEATPORT_MERGED_COLUMNS, [asdict(row) for row in merged_rows])

        logger.info(
            "Beatport enrichment complete: input=%d discarded=%d output=%d matched_isrc=%d matched_fallback=%d unmatched=%d ambiguous_isrc=%d ambiguous_fallback=%d fallback_ties=%d output_path=%s",
            stats.input_rows,
            stats.discarded_seed_rows,
            stats.output_rows,
            stats.isrc_matches,
            stats.title_artist_fallback_matches,
            stats.no_match_rows,
            stats.ambiguous_isrc_rows,
            stats.ambiguous_fallback_rows,
            stats.fallback_equal_rank_ties,
            output_csv,
        )
        return stats

    def enrich_beatport_seed_csv(
        self,
        input_csv: Path,
        output_csv: Path,
    ) -> BeatportTidalEnrichmentStats:
        """Enrich a Beatport seed CSV row-by-row using TIDAL-only lookup."""
        provider = self._get_provider("tidal")
        if provider is None or not hasattr(provider, "enrich_beatport_seed_row"):
            raise RuntimeError("TIDAL provider is unavailable for seed enrichment")

        seed_rows, input_rows, discarded_rows = self._load_beatport_seed_rows(input_csv)
        stats = BeatportTidalEnrichmentStats(
            input_rows=input_rows,
            discarded_seed_rows=discarded_rows,
        )
        merged_rows: List[BeatportTidalMergedRow] = []
        for seed_row in seed_rows:
            merged_row, telemetry = cast(
                tuple[BeatportTidalMergedRow, Dict[str, int]],
                provider.enrich_beatport_seed_row(seed_row),
            )
            merged_rows.append(merged_row)
            stats.output_rows += 1
            stats.ambiguous_isrc_rows += telemetry.get("ambiguous_isrc_rows", 0)
            stats.ambiguous_fallback_rows += telemetry.get("ambiguous_fallback_rows", 0)
            stats.fallback_equal_rank_ties += telemetry.get("fallback_equal_rank_ties", 0)
            if merged_row.match_method == "isrc":
                stats.isrc_matches += 1
            elif merged_row.match_method == "title_artist_fallback":
                stats.title_artist_fallback_matches += 1
            elif merged_row.match_method == "no_match":
                stats.no_match_rows += 1

        self._write_csv_rows(output_csv, BEATPORT_TIDAL_MERGED_COLUMNS, [asdict(row) for row in merged_rows])

        logger.info(
            "Tidal enrichment complete: input=%d discarded=%d output=%d matched_isrc=%d matched_fallback=%d unmatched=%d ambiguous_isrc=%d ambiguous_fallback=%d fallback_ties=%d output_path=%s",
            stats.input_rows,
            stats.discarded_seed_rows,
            stats.output_rows,
            stats.isrc_matches,
            stats.title_artist_fallback_matches,
            stats.no_match_rows,
            stats.ambiguous_isrc_rows,
            stats.ambiguous_fallback_rows,
            stats.fallback_equal_rank_ties,
            output_csv,
        )
        return stats

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
            router=self.router,
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
            router=self.router,
            path_pattern=path_pattern,
            limit=limit,
            force=force,
            retry_no_match=retry_no_match,
            zones=zones,
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
            router=self.router,
            force=force,
            retry_no_match=retry_no_match,
        )
