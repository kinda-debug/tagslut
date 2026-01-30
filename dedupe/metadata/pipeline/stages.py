"""Pipeline stages for metadata enrichment."""

import logging
from typing import List

from dedupe.metadata.models.types import (
    ProviderTrack,
    EnrichmentResult,
    LocalFileInfo,
    MatchConfidence,
    MetadataHealth,
)
from dedupe.metadata.models.precedence import (
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
from dedupe.metadata.providers.base import classify_match_confidence

logger = logging.getLogger("dedupe.metadata.enricher")


def resolve_file(
    file_info: LocalFileInfo,
    provider_names: List[str],
    provider_getter,
    mode: str,
) -> EnrichmentResult:
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

    def normalize_title(value: str) -> str:
        cleaned = value.lower().strip()
        for suffix in ("(original mix)", "(main mix)"):
            cleaned = cleaned.replace(suffix, "").strip()
        return " ".join(cleaned.split())

    # Stage 0: Beatport track ID (from MP3Tag tags) if available
    beatport_id = None
    if file_info.beatport_id:
        beatport_id = file_info.beatport_id.strip()
    elif file_info.beatport_track_url:
        # Extract numeric ID from Beatport track URL
        # Examples: https://www.beatport.com/track/around-the-world/35743543
        url = file_info.beatport_track_url.strip()
        if url:
            parts = url.rstrip("/").split("/")
            if parts:
                candidate = parts[-1]
                if candidate.isdigit():
                    beatport_id = candidate

    if beatport_id:
        provider = provider_getter("beatport")
        if provider and "beatport" in provider_names:
            log(f"Trying Beatport track ID: {beatport_id}")
            track = provider.fetch_by_id(beatport_id)
            if track:
                track.match_confidence = MatchConfidence.EXACT
                matches.append(track)
                log(f"  beatport: ID match -> {track.title} by {track.artist}")

    # Stage 0b: Beatport release ID/URL (from MP3Tag tags) if available
    if not matches:
        release_id = None
        release_slug = None
        if file_info.beatport_release_id:
            release_id = file_info.beatport_release_id.strip()
        elif file_info.beatport_release_url:
            url = file_info.beatport_release_url.strip()
            if url:
                parts = url.rstrip("/").split("/")
                if len(parts) >= 2:
                    candidate = parts[-1]
                    if candidate.isdigit():
                        release_id = candidate
                        release_slug = parts[-2]
        if release_id:
            provider = provider_getter("beatport")
            if provider and "beatport" in provider_names:
                log(f"Trying Beatport release ID: {release_id}")
                release_tracks = provider.fetch_release_tracks(release_id, slug=release_slug)
                if release_tracks and file_info.tag_title:
                    wanted = normalize_title(file_info.tag_title)
                    for t in release_tracks:
                        if t.title and normalize_title(t.title) == wanted:
                            t.match_confidence = MatchConfidence.EXACT
                            matches.append(t)
                            log(f"  beatport: release match -> {t.title} by {t.artist}")
                            break

    # Stage 1: Try ISRC if available
    if file_info.tag_isrc:
        log(f"Trying ISRC: {file_info.tag_isrc}")
        for provider_name in provider_names:
            provider = provider_getter(provider_name)
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

        for provider_name in provider_names:
            provider = provider_getter(provider_name)
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
        for provider_name in provider_names:
            provider = provider_getter(provider_name)
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
    if mode in ("hoarding", "both"):
        spotify_provider = provider_getter("spotify")
        if spotify_provider and hasattr(spotify_provider, 'enrich_with_audio_features'):
            for m in matches:
                if m.service == "spotify" and m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG):
                    spotify_provider.enrich_with_audio_features(m)
                    log(f"  spotify: enriched with audio features (BPM={m.bpm}, key={m.key})")

    # Apply cascade rules to get canonical values
    if matches:
        result = apply_cascade(result, file_info, mode)
        result.enrichment_providers = list(set(m.service for m in matches))

        # Set overall confidence
        best_confidence = max(m.match_confidence for m in matches)
        result.enrichment_confidence = best_confidence
    else:
        log("No matches found")
        result.metadata_health = MetadataHealth.UNKNOWN
        result.metadata_health_reason = "no_provider_match"

    return result


def apply_cascade(
    result: EnrichmentResult,
    file_info: LocalFileInfo,
    mode: str,
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
    if mode in ("recovery", "both"):
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
                result.metadata_health, result.metadata_health_reason = classify_health(
                    file_info.measured_duration_s,
                    duration,
                )

    # HOARDING MODE: Full metadata (require high-confidence)
    if mode in ("hoarding", "both"):
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


def classify_health(
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
