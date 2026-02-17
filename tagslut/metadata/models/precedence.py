"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic
DURATION_PRECEDENCE = ["beatport", "tidal", "deezer", "apple_music", "spotify", "itunes"]

# DJ metadata - Beatport specializes in this
BPM_PRECEDENCE = ["beatport", "spotify"]  # Only these have BPM
KEY_PRECEDENCE = ["beatport", "spotify"]  # Only these have key
GENRE_PRECEDENCE = ["beatport", "tidal", "deezer", "apple_music", "spotify", "itunes"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport
LABEL_PRECEDENCE = ["beatport", "apple_music", "tidal", "deezer", "spotify"]
CATALOG_NUMBER_PRECEDENCE = ["beatport"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "spotify", "itunes"]
ARTIST_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "spotify", "itunes"]
ALBUM_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "spotify", "itunes"]

# Artwork - hi-res services first (Apple Music has high-res artwork)
ARTWORK_PRECEDENCE = ["tidal", "apple_music", "deezer", "spotify", "beatport", "itunes"]

# Composer - Apple Music has good composer data
COMPOSER_PRECEDENCE = ["apple_music", "tidal", "spotify"]

# ISRC - all major services have this, Apple Music is reliable
ISRC_PRECEDENCE = ["beatport", "apple_music", "tidal", "deezer", "spotify"]

# Spotify audio features - only Spotify has these
AUDIO_FEATURES_SOURCE = "spotify"
