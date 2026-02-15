"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic, Qobuz for classical
DURATION_PRECEDENCE = ["beatport", "qobuz", "tidal", "apple_music", "spotify", "itunes"]

# DJ metadata - Beatport specializes in this
BPM_PRECEDENCE = ["beatport", "spotify"]  # Only these have BPM
KEY_PRECEDENCE = ["beatport", "spotify"]  # Only these have key
GENRE_PRECEDENCE = ["beatport", "qobuz", "tidal", "apple_music", "spotify", "itunes"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport/Qobuz
LABEL_PRECEDENCE = ["beatport", "qobuz", "apple_music", "tidal", "spotify"]
CATALOG_NUMBER_PRECEDENCE = ["beatport", "qobuz"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["qobuz", "tidal", "apple_music", "beatport", "spotify", "itunes"]
ARTIST_PRECEDENCE = ["qobuz", "tidal", "apple_music", "beatport", "spotify", "itunes"]
ALBUM_PRECEDENCE = ["qobuz", "tidal", "apple_music", "beatport", "spotify", "itunes"]

# Artwork - hi-res services first (Apple Music has high-res artwork)
ARTWORK_PRECEDENCE = ["qobuz", "tidal", "apple_music", "spotify", "beatport", "itunes"]

# Composer - Apple Music and Qobuz have good classical/composer data
COMPOSER_PRECEDENCE = ["apple_music", "qobuz", "tidal", "spotify"]

# ISRC - all major services have this, Apple Music is reliable
ISRC_PRECEDENCE = ["beatport", "apple_music", "qobuz", "tidal", "spotify"]

# Spotify audio features - only Spotify has these
AUDIO_FEATURES_SOURCE = "spotify"
