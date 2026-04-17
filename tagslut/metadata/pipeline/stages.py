"""Pipeline stages for metadata enrichment."""

import logging
import re
from typing import List

from tagslut.metadata.models.types import (
    ProviderTrack,
    EnrichmentResult,
    LocalFileInfo,
    MatchConfidence,
    MetadataHealth,
)
from tagslut.metadata.models.precedence import (
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
)
from tagslut.metadata.providers.base import classify_match_confidence
from tagslut.metadata.capabilities import Capability
from tagslut.metadata.genre_normalization import default_genre_normalizer
from tagslut.metadata.metadata_router import DEFAULT_ISRC_FALLBACK_POLICY, ISRCResolutionFallbackPolicy

logger = logging.getLogger("tagslut.metadata.enricher")
ISRC_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$")


def normalize_title(value: str) -> str:
    """Normalize a title for matching (e.g. remove common mix suffixes)."""
    cleaned = value.lower().strip()
    for suffix in ("(original mix)", "(main mix)"):
        cleaned = cleaned.replace(suffix, "").strip()
    return " ".join(cleaned.split())


def normalize_isrc(value: str) -> str | None:
    """
    Extract the first valid ISRC from a tag value.

    Some files carry multiple ISRCs in one tag, separated by ';', ',' or spaces.
    Providers expect a single 12-character ISRC token.
    """
    if not value:
        return None
    for token in re.split(r"[;,|\s/]+", value):
        candidate = token.strip().upper()
        if candidate and ISRC_PATTERN.match(candidate):
            return candidate
    return None


def resolve_file(  # type: ignore  # TODO: mypy-strict
    file_info: LocalFileInfo,
    provider_names: List[str],
    provider_getter,
    mode: str,
    *,
    router,
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
        if "beatport" in router.provider_names_for(Capability.METADATA_FETCH_TRACK_BY_ID, log=log):
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
            if "beatport" in router.provider_names_for(Capability.METADATA_FETCH_TRACK_BY_ID, log=log):
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
    normalized_isrc = normalize_isrc(file_info.tag_isrc) if file_info.tag_isrc else None
    if normalized_isrc:
        log(f"Trying ISRC: {normalized_isrc}")
        isrc_providers = router.provider_names_for(Capability.METADATA_SEARCH_BY_ISRC, log=log)
        if not isrc_providers:
            if DEFAULT_ISRC_FALLBACK_POLICY == ISRCResolutionFallbackPolicy.PROCEED_UNCERTAIN:
                result.ingestion_confidence = "uncertain"
                log("ISRC search unavailable across providers; proceeding with uncertain fallback")
            else:
                log("ISRC search unavailable across providers; skipping ISRC stage")
        for provider_name in [p for p in provider_names if p in isrc_providers]:
            provider = provider_getter(provider_name)
            if provider is None:
                continue

            if provider_name == "reccobeats":
                tidal_bpm_present = any(
                    (m.service == "tidal")
                    and (getattr(m, "tidal_bpm", None) is not None or getattr(m, "bpm", None) is not None)
                    for m in matches
                )
                if tidal_bpm_present:
                    log("  reccobeats: skipping ISRC lookup (TIDAL already provides BPM)")
                    continue

            isrc_matches = provider.search_by_isrc(normalized_isrc)
            for m in isrc_matches:
                m.match_confidence = MatchConfidence.EXACT
                matches.append(m)
                log(f"  {provider_name}: ISRC match -> {m.title} by {m.artist}")
    elif file_info.tag_isrc:
        log(f"Skipping malformed ISRC tag: {file_info.tag_isrc}")

    # Stage 2: Try artist + title search if no ISRC matches
    if not matches and file_info.tag_artist and file_info.tag_title:
        query = f"{file_info.tag_artist} {file_info.tag_title}"
        log(f"Trying text search: {query}")

        text_providers = router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT, log=log)
        for provider_name in [p for p in provider_names if p in text_providers]:
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
        text_providers = router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT, log=log)
        for provider_name in [p for p in provider_names if p in text_providers]:
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

    # Stage 4 (hoarding only): Fill gaps by searching providers that didn't
    # match in earlier stages.  If ISRC or Beatport-ID matched one provider but
    # others had no result, text search those remaining providers so we maximise
    # metadata coverage (e.g. get key from Tidal when Beatport lacked it).
    if mode in ("hoarding", "both") and matches and file_info.tag_artist and file_info.tag_title:
        matched_services = {m.service for m in matches}
        missing_providers = [p for p in provider_names if p not in matched_services]
        if missing_providers:
            query = f"{file_info.tag_artist} {file_info.tag_title}"
            log(f"Hoarding gap-fill: text search on {missing_providers}")
            for provider_name in missing_providers:
                if provider_name not in router.provider_names_for(Capability.METADATA_SEARCH_BY_TEXT, log=log):
                    continue
                provider = provider_getter(provider_name)
                if provider is None:
                    continue

                search_results = provider.search(query, limit=5)
                for track in search_results:
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

    # Store all matches
    result.matches = matches

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
        if m.match_confidence in (
            MatchConfidence.EXACT, MatchConfidence.STRONG,
            MatchConfidence.MEDIUM, MatchConfidence.WEAK,
        )
    ]

    # For HOARDING: require high-confidence matches
    hoarding_usable = [
        m for m in matches
        if m.match_confidence in (MatchConfidence.EXACT, MatchConfidence.STRONG)
    ]

    # Helper to pick value by precedence
    def pick_by_precedence(  # type: ignore  # TODO: mypy-strict
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
                result.canonical_isrc = normalize_isrc(file_info.tag_isrc) or file_info.tag_isrc
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

            sub_genre, _ = pick_by_precedence(
                SUB_GENRE_PRECEDENCE, lambda m: m.sub_genre, hoarding_usable)
            genre, sub_genre = default_genre_normalizer().normalize_pair(genre, sub_genre)
            result.canonical_genre = genre
            result.canonical_sub_genre = sub_genre

            # Release info
            label, _ = pick_by_precedence(LABEL_PRECEDENCE, lambda m: m.label, hoarding_usable)
            result.canonical_label = label

            catalog_num, _ = pick_by_precedence(
                CATALOG_NUMBER_PRECEDENCE, lambda m: m.catalog_number, hoarding_usable)
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
            artwork, _ = pick_by_precedence(
                ARTWORK_PRECEDENCE, lambda m: m.album_art_url, hoarding_usable)
            result.canonical_album_art_url = artwork

            # Provider IDs for linking
            for m in hoarding_usable:
                if not m.service_track_id:
                    continue
                if m.service == "beatport":
                    result.beatport_id = m.service_track_id
                elif m.service == "tidal":
                    result.tidal_id = m.service_track_id

            # Audio features from ReccoBeats (lowest priority — fills never-populated fields only)
            reccobeats_result = next((m for m in hoarding_usable if m.service == "reccobeats"), None)
            if reccobeats_result:
                if result.canonical_energy is None and reccobeats_result.energy is not None:
                    result.canonical_energy = reccobeats_result.energy
                if result.canonical_danceability is None and reccobeats_result.danceability is not None:
                    result.canonical_danceability = reccobeats_result.danceability
                if result.canonical_valence is None and reccobeats_result.valence is not None:
                    result.canonical_valence = reccobeats_result.valence
                if result.canonical_acousticness is None and reccobeats_result.acousticness is not None:
                    result.canonical_acousticness = reccobeats_result.acousticness
                if result.canonical_instrumentalness is None and reccobeats_result.instrumentalness is not None:
                    result.canonical_instrumentalness = reccobeats_result.instrumentalness
                if result.canonical_loudness is None and reccobeats_result.loudness is not None:
                    result.canonical_loudness = reccobeats_result.loudness
                # BPM: only use ReccoBeats tempo if no BPM from authoritative sources
                if result.canonical_bpm is None and reccobeats_result.bpm is not None:
                    result.canonical_bpm = reccobeats_result.bpm

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
