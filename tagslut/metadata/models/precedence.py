"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic
DURATION_PRECEDENCE = ["beatport", "tidal", "deezer", "apple_music", "itunes"]

# DJ metadata - Beatport specializes in this
BPM_PRECEDENCE = ["beatport"]  # Spotify disabled
KEY_PRECEDENCE = ["beatport"]  # Spotify disabled
GENRE_PRECEDENCE = ["beatport", "tidal", "deezer", "apple_music", "itunes"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport
LABEL_PRECEDENCE = ["beatport", "apple_music", "tidal", "deezer"]
CATALOG_NUMBER_PRECEDENCE = ["beatport"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "itunes"]
ARTIST_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "itunes"]
ALBUM_PRECEDENCE = ["tidal", "apple_music", "beatport", "deezer", "itunes"]

# Artwork - hi-res services first (Apple Music has high-res artwork)
ARTWORK_PRECEDENCE = ["tidal", "apple_music", "deezer", "beatport", "itunes"]

# Composer - Apple Music has good composer data
COMPOSER_PRECEDENCE = ["apple_music", "tidal"]

# ISRC - all major services have this, Apple Music is reliable
ISRC_PRECEDENCE = ["beatport", "apple_music", "tidal", "deezer"]

# Spotify audio features - only Spotify has these
AUDIO_FEATURES_SOURCE = ""
