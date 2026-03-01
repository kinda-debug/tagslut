"""Pipeline runner for metadata enrichment."""

import logging
from dataclasses import dataclass
from typing import List, Optional

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo
from tagslut.metadata.store import db_reader, db_writer
from tagslut.metadata.pipeline import stages

logger = logging.getLogger("tagslut.metadata.enricher")


@dataclass
class EnrichmentStats:
    """Statistics from an enrichment run."""
    total: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    no_match: int = 0
    no_match_files: List[str] = None  # type: ignore  # TODO: mypy-strict  # Paths of files with no match

    def __post_init__(self):  # type: ignore  # TODO: mypy-strict
        if self.no_match_files is None:
            self.no_match_files = []


def run_enrich_all(  # type: ignore  # TODO: mypy-strict
    db_path,
    provider_names: List[str],
    provider_getter,
    mode: str,
    dry_run: bool,
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
    stats = EnrichmentStats()

    # Get all eligible files
    hoarding_mode = mode in ("hoarding", "both")
    files = list(db_reader.get_eligible_files(
        db_path, path_pattern, limit, force, retry_no_match, zones,
        hoarding_mode=hoarding_mode,
    ))
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
                result = stages.resolve_file(file_info, provider_names, provider_getter, mode)

                if not result.matches:
                    stats.no_match += 1
                    stats.no_match_files.append(file_info.path)
                    # Mark as processed with no_match so we don't retry
                    db_writer.mark_no_match(db_path, file_info.path, dry_run)
                    logger.info("NO MATCH: %s (searched: %s %s)",
                                file_info.path,
                                file_info.tag_artist or "?",
                                file_info.tag_title or "?")
                    continue

                # Update database
                if db_writer.update_database(db_path, result, dry_run, mode):
                    stats.enriched += 1
                    # Log match details
                    best_match = max(
                        result.matches, key=lambda m: m.match_confidence.value if m.match_confidence else 0)
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


def run_enrich_file(  # type: ignore  # TODO: mypy-strict
    db_path,
    provider_names: List[str],
    provider_getter,
    mode: str,
    dry_run: bool,
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
    row = db_reader.get_file_row(db_path, path)

    if not row:
        return None, "not_found"

    flac_ok = row["flac_ok"]
    if flac_ok is not None and int(flac_ok) != 1 and not force:
        return None, "not_flac_ok"

    if not force:
        already = row["enriched_at"] is not None
        if retry_no_match:
            if already and row["metadata_health_reason"] != "no_provider_match":
                return None, "not_eligible"
        else:
            if already:
                return None, "not_eligible"

    file_info = db_reader.row_to_local_file_info(row)
    result = stages.resolve_file(file_info, provider_names, provider_getter, mode)

    if not result.matches:
        db_writer.mark_no_match(db_path, file_info.path, dry_run)
        return result, "no_match"

    if db_writer.update_database(db_path, result, dry_run, mode):
        return result, "enriched"

    return result, "failed"


def run_get_file_info(db_path, path: str) -> Optional[LocalFileInfo]:  # type: ignore  # TODO: mypy-strict
    """Compatibility helper for fetching a single file info."""
    return db_reader.get_file_info(db_path, path)
