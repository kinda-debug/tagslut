"""Database write helpers for metadata enrichment."""

import json
import logging
import sqlite3
from datetime import datetime

from dedupe.metadata.models.types import EnrichmentResult

logger = logging.getLogger("dedupe.metadata.enricher")


def update_database(db_path, result: EnrichmentResult, dry_run: bool, mode: str) -> bool:
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
    if dry_run:
        logger.info("[DRY-RUN] Would update %s (mode=%s)", result.path, mode)
        return True

    conn = sqlite3.connect(db_path)
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
        if mode in ("recovery", "both"):
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
        if mode in ("hoarding", "both"):
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


def mark_no_match(db_path, path: str, dry_run: bool) -> None:
    """Mark a file as processed but with no provider match."""
    if dry_run:
        return

    conn = sqlite3.connect(db_path)
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
