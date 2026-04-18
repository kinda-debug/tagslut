"""Pipeline runner for metadata enrichment."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from tagslut.metadata.models.types import EnrichmentResult, LocalFileInfo, MatchConfidence
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
    # Hoarding field counters
    bpm_filled: int = 0
    key_filled: int = 0
    genre_filled: int = 0
    label_filled: int = 0
    artwork_filled: int = 0
    # Undertagged: enriched tracks missing one or more critical fields
    # Each entry is a tuple: (display_name: str, missing_fields: list[str])
    undertagged: List[tuple[str, List[str]]] = None  # type: ignore  # TODO: mypy-strict

    def __post_init__(self):  # type: ignore  # TODO: mypy-strict
        if self.no_match_files is None:
            self.no_match_files = []
        if self.undertagged is None:
            self.undertagged = []


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _display_name(file_info: LocalFileInfo) -> str:
    artist = (file_info.tag_artist or "").strip()
    title = (file_info.tag_title or "").strip()
    if artist and title:
        return f"{artist} - {title}"[:45]
    return Path(file_info.path).stem[:45]


def _format_track_line(
    index: int,
    total: int,
    file_info: LocalFileInfo,
    result: Optional[EnrichmentResult],
    *,
    failed: bool,
    mode: str,
) -> str:
    name = _display_name(file_info)

    if failed:
        status = "✗"
        detail = "failed"
    elif result is None or result.enrichment_confidence == MatchConfidence.NONE:
        status = "✗"
        detail = "no match"
    else:
        status = "✓"
        seen_services: set[str] = set()
        provider_order: list[str] = []
        for match in (result.matches or []):
            service = (match.service or "").strip()
            if not service or service in seen_services:
                continue
            seen_services.add(service)
            provider_order.append(service)

        winner = result.matches[0].service if result.matches else "?"
        provider = winner
        if len(provider_order) > 1:
            provider = f"{winner} [{' -> '.join(provider_order)}]"
        confidence = result.enrichment_confidence.value if result.enrichment_confidence else ""
        detail = f"{provider} ({confidence})"

        if mode in ("hoarding", "both"):
            missing: List[str] = []
            if not _present(getattr(result, "canonical_bpm", None)):
                missing.append("BPM")
            if not _present(getattr(result, "canonical_key", None)):
                missing.append("key")
            if not _present(getattr(result, "canonical_genre", None)):
                missing.append("genre")
            if not _present(getattr(result, "canonical_label", None)):
                missing.append("label")

            status = "~" if missing else "✓"

            if _present(getattr(result, "canonical_bpm", None)):
                detail += f"  BPM:{int(result.canonical_bpm)}"
            if _present(getattr(result, "canonical_key", None)):
                detail += f" Key:{result.canonical_key}"
            if missing:
                detail += f"  no {', '.join(missing)}"

    counter = f"[{index}/{total}]"
    return f"{counter:<8} {name:<45} {status}  {detail}"


def run_enrich_all(  # type: ignore  # TODO: mypy-strict
    db_path,
    provider_names: List[str],
    provider_getter,
    mode: str,
    dry_run: bool,
    *,
    router,
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
            # Checkpoint logging (quieter - only to log file)
            if (i + 1) % checkpoint_interval == 0:
                logger.debug(
                    "Checkpoint %d/%d: enriched=%d, no_match=%d, failed=%d",
                    i + 1, stats.total, stats.enriched, stats.no_match, stats.failed
                )

            try:
                # Resolve and enrich
                result = stages.resolve_file(file_info, provider_names, provider_getter, mode, router=router)

                if not result.matches:
                    stats.no_match += 1
                    stats.no_match_files.append(file_info.path)
                    # Mark as processed with no_match so we don't retry
                    db_writer.mark_no_match(db_path, file_info.path, dry_run)
                    logger.info("NO MATCH: %s (searched: %s %s)",
                                file_info.path,
                                file_info.tag_artist or "?",
                                file_info.tag_title or "?")
                    print(
                        _format_track_line(i + 1, stats.total, file_info, result, failed=False, mode=mode),
                        flush=True,
                    )
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
                    if hoarding_mode:
                        bpm_ok = _present(getattr(result, "canonical_bpm", None)) or _present(getattr(result, "beatport_bpm", None))
                        key_ok = _present(getattr(result, "canonical_key", None)) or _present(getattr(result, "beatport_key", None))
                        genre_ok = _present(getattr(result, "canonical_genre", None)) or _present(getattr(result, "beatport_genre", None))
                        label_ok = _present(getattr(result, "canonical_label", None)) or _present(getattr(result, "beatport_label", None))
                        artwork_ok = _present(getattr(result, "canonical_album_art_url", None))

                        if not bpm_ok:
                            bpm_ok = any(_present(getattr(m, "bpm", None)) for m in (result.matches or []))
                        if not key_ok:
                            key_ok = any(_present(getattr(m, "key", None)) for m in (result.matches or []))
                        if not genre_ok:
                            genre_ok = any(_present(getattr(m, "genre", None)) for m in (result.matches or []))
                        if not label_ok:
                            label_ok = any(_present(getattr(m, "label", None)) for m in (result.matches or []))
                        if not artwork_ok:
                            artwork_ok = any(_present(getattr(m, "album_art_url", None)) for m in (result.matches or []))

                        if bpm_ok:
                            stats.bpm_filled += 1
                        if key_ok:
                            stats.key_filled += 1
                        if genre_ok:
                            stats.genre_filled += 1
                        if label_ok:
                            stats.label_filled += 1
                        if artwork_ok:
                            stats.artwork_filled += 1

                        missing: List[str] = []
                        if not bpm_ok:
                            missing.append("BPM")
                        if not key_ok:
                            missing.append("key")
                        if not genre_ok:
                            missing.append("genre")
                        if not label_ok:
                            missing.append("label")

                        if missing:
                            artist = (getattr(result, "canonical_artist", None) or best_match.artist or file_info.tag_artist or "").strip()
                            title = (getattr(result, "canonical_title", None) or best_match.title or file_info.tag_title or "").strip()
                            name = f"{artist} - {title}".strip(" -") if (artist or title) else file_info.path
                            stats.undertagged.append((name, missing))
                    print(
                        _format_track_line(i + 1, stats.total, file_info, result, failed=False, mode=mode),
                        flush=True,
                    )
                else:
                    stats.failed += 1
                    logger.warning("FAILED to update: %s", file_info.path)
                    print(
                        _format_track_line(i + 1, stats.total, file_info, result, failed=True, mode=mode),
                        flush=True,
                    )

            except KeyboardInterrupt:
                raise  # Re-raise to outer handler
            except Exception as e:
                logger.warning("Error processing %s: %s", file_info.path, e)
                stats.failed += 1
                print(
                    _format_track_line(i + 1, stats.total, file_info, None, failed=True, mode=mode),
                    flush=True,
                )
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
    router,
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
    result = stages.resolve_file(file_info, provider_names, provider_getter, mode, router=router)

    if not result.matches:
        db_writer.mark_no_match(db_path, file_info.path, dry_run)
        return result, "no_match"

    if db_writer.update_database(db_path, result, dry_run, mode):
        return result, "enriched"

    return result, "failed"


def run_get_file_info(db_path, path: str) -> Optional[LocalFileInfo]:  # type: ignore  # TODO: mypy-strict
    """Compatibility helper for fetching a single file info."""
    return db_reader.get_file_info(db_path, path)
