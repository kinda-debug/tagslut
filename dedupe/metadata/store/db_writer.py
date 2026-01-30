"""Database write helpers for metadata enrichment.

This module is responsible for persisting enrichment outcomes to SQLite.

In addition to updating the per-file record in the `files` table, we also
maintain a track-level hub for provenance and cross-file consolidation:

- `library_tracks`: canonical track entity (one row per logical track)
- `library_track_sources`: per-provider snapshots (raw payload + confidence)

The track hub enables later reconciliation, auditing, and stable linking
between many file paths and a single track identity.
"""

import hashlib
import json
import logging
import re
import sqlite3
import unicodedata
from datetime import datetime

from dedupe.metadata.models.types import EnrichmentResult, ProviderTrack

logger = logging.getLogger("dedupe.metadata.enricher")


def _normalize_key_component(value: str) -> str:
    """Normalize a string for use in a deterministic key.

    - Unicode NFKD normalize
    - ASCII fold (drop combining marks)
    - lowercase
    - keep alnum, convert others to single spaces
    - collapse whitespace into single '-'
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "-")


def _bucket_duration_ms(duration_ms: int | None) -> int | None:
    """Bucket duration to reduce key fragmentation.

    Uses 2-second buckets (in ms). This avoids generating different keys
    for tiny duration reporting differences between providers.
    """
    if duration_ms is None:
        return None
    if duration_ms <= 0:
        return None
    bucket_s = int(round((duration_ms / 1000.0) / 2.0) * 2)
    return bucket_s * 1000


def _derive_library_track_key(result: EnrichmentResult) -> str:
    """Derive a stable track key for linking files to a logical track entity.

    Priority:
      1) ISRC (best cross-provider key)
      2) provider IDs (stable per-provider)
      3) normalized artist/title + duration bucket
      4) last-resort hash of path (to avoid NULL keys)
    """
    best: ProviderTrack | None = None
    if result.matches:
        rank = {
            "exact": 4,
            "strong": 3,
            "medium": 2,
            "weak": 1,
            "none": 0,
        }
        best = max(
            result.matches,
            key=lambda m: rank.get(getattr(getattr(m, "match_confidence", None), "value", "none"), 0),
        )

    if result.canonical_isrc:
        return f"isrc:{result.canonical_isrc.strip().upper()}"
    if best and best.isrc:
        return f"isrc:{best.isrc.strip().upper()}"

    for prefix, value in (
        ("spotify", result.spotify_id),
        ("beatport", result.beatport_id),
        ("tidal", result.tidal_id),
        ("qobuz", result.qobuz_id),
        ("itunes", result.itunes_id),
    ):
        if value:
            return f"{prefix}:{str(value).strip()}"

    if best and best.service and best.service_track_id:
        return f"{best.service}:{str(best.service_track_id).strip()}"

    artist = _normalize_key_component(result.canonical_artist or (best.artist if best else "") or "")
    title = _normalize_key_component(result.canonical_title or (best.title if best else "") or "")

    duration_ms = None
    if result.canonical_duration is not None:
        try:
            duration_ms = int(round(float(result.canonical_duration) * 1000.0))
        except (TypeError, ValueError):
            duration_ms = None
    if duration_ms is None and best and best.duration_ms:
        duration_ms = int(best.duration_ms)
    duration_ms = _bucket_duration_ms(duration_ms)

    if artist or title:
        dur_part = f"d{duration_ms}" if duration_ms else "d?"
        # Truncate to keep keys reasonable
        artist = artist[:80]
        title = title[:120]
        return f"at:{artist}__{title}__{dur_part}"

    # Last resort: stable hash of the file path string
    digest = hashlib.sha1(result.path.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"path:{digest}"


def _upsert_library_track(conn: sqlite3.Connection, key: str, result: EnrichmentResult) -> None:
    """Upsert canonical track row (library_tracks) with null-safe updates."""
    # Map enrichment canonical fields to library_tracks columns.
    # In recovery-only runs, canonical identity fields may not be set; fall back
    # to the best available provider match to keep the hub usable.
    best: ProviderTrack | None = None
    if result.matches:
        rank = {
            "exact": 4,
            "strong": 3,
            "medium": 2,
            "weak": 1,
            "none": 0,
        }
        best = max(
            result.matches,
            key=lambda m: rank.get(getattr(getattr(m, "match_confidence", None), "value", "none"), 0),
        )

    title = result.canonical_title or (best.title if best else None)
    artist = result.canonical_artist or (best.artist if best else None)
    album = result.canonical_album or (best.album if best else None)
    isrc = result.canonical_isrc or (best.isrc if best else None)
    release_date = result.canonical_release_date or (best.release_date if best else None)
    cover_url = result.canonical_album_art_url or (best.album_art_url if best else None)
    genre = result.canonical_genre or (best.genre if best else None)
    bpm = result.canonical_bpm or (best.bpm if best else None)
    musical_key = result.canonical_key or (best.key if best else None)
    label = result.canonical_label or (best.label if best else None)

    duration_ms = None
    if result.canonical_duration is not None:
        try:
            duration_ms = int(round(float(result.canonical_duration) * 1000.0))
        except (TypeError, ValueError):
            duration_ms = None
    if duration_ms is None and best and best.duration_ms:
        duration_ms = int(best.duration_ms)

    conn.execute(
        """
        INSERT INTO library_tracks (
            library_track_key,
            title,
            artist,
            album,
            duration_ms,
            isrc,
            release_date,
            explicit,
            best_cover_url,
            genre,
            bpm,
            musical_key,
            label,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(library_track_key) DO UPDATE SET
            title = COALESCE(excluded.title, library_tracks.title),
            artist = COALESCE(excluded.artist, library_tracks.artist),
            album = COALESCE(excluded.album, library_tracks.album),
            duration_ms = COALESCE(excluded.duration_ms, library_tracks.duration_ms),
            isrc = COALESCE(excluded.isrc, library_tracks.isrc),
            release_date = COALESCE(excluded.release_date, library_tracks.release_date),
            explicit = COALESCE(excluded.explicit, library_tracks.explicit),
            best_cover_url = COALESCE(excluded.best_cover_url, library_tracks.best_cover_url),
            genre = COALESCE(excluded.genre, library_tracks.genre),
            bpm = COALESCE(excluded.bpm, library_tracks.bpm),
            musical_key = COALESCE(excluded.musical_key, library_tracks.musical_key),
            label = COALESCE(excluded.label, library_tracks.label),
            updated_at = CURRENT_TIMESTAMP
        ;
        """,
        (
            key,
            title,
            artist,
            album,
            duration_ms,
            isrc,
            release_date,
            (1 if result.canonical_explicit else 0) if result.canonical_explicit is not None else None,
            cover_url,
            genre,
            bpm,
            musical_key,
            label,
        ),
    )


def _upsert_library_track_source(
    conn: sqlite3.Connection,
    key: str,
    match: ProviderTrack,
) -> None:
    """Insert (or replace) a provider snapshot row for a track."""

    # Avoid duplicates without requiring a unique constraint:
    # delete existing row for (key, service, service_track_id) then insert.
    conn.execute(
        """
        DELETE FROM library_track_sources
        WHERE library_track_key = ? AND service = ? AND service_track_id = ?
        """,
        (key, match.service, match.service_track_id),
    )

    conn.execute(
        """
        INSERT INTO library_track_sources (
            library_track_key,
            service,
            service_track_id,
            url,
            metadata_json,
            duration_ms,
            isrc,
            album_art_url,
            genre,
            bpm,
            musical_key,
            album_title,
            artist_name,
            track_number,
            disc_number,
            match_confidence,
            fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            key,
            match.service,
            match.service_track_id,
            match.url,
            json.dumps(match.raw) if match.raw else None,
            match.duration_ms,
            match.isrc,
            match.album_art_url,
            match.genre,
            match.bpm,
            match.key,
            match.album,
            match.artist,
            match.track_number,
            match.disc_number,
            match.match_confidence.value if match.match_confidence else None,
        ),
    )



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

        # Derive or reuse a track-hub key and persist the hub/sources.
        library_track_key = _derive_library_track_key(result)

        # Ensure canonical track hub and provenance snapshots exist.
        # This is safe to call even if mode is "recovery" because it doesn't
        # require DJ metadata; it will only fill what we have.
        _upsert_library_track(conn, library_track_key, result)
        for match in (result.matches or []):
            try:
                _upsert_library_track_source(conn, library_track_key, match)
            except sqlite3.Error as e:
                logger.debug(
                    "Failed to upsert source snapshot (service=%s id=%s): %s",
                    getattr(match, "service", None),
                    getattr(match, "service_track_id", None),
                    e,
                )

        # Build dynamic UPDATE based on mode
        fields = []
        values = []

        # Always write enriched_at, providers, confidence, and track-hub key
        fields.extend([
            "enriched_at = ?",
            "enrichment_providers = ?",
            "enrichment_confidence = ?",
            "library_track_key = ?",
        ])
        values.extend([
            datetime.utcnow().isoformat(),
            json.dumps(result.enrichment_providers) if result.enrichment_providers else None,
            result.enrichment_confidence.value if result.enrichment_confidence else None,
            library_track_key,
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
