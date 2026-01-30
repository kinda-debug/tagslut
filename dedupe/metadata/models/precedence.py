"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic, Qobuz for classical
DURATION_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify", "itunes"]

# DJ metadata - Beatport specializes in this
BPM_PRECEDENCE = ["beatport", "spotify"]  # Only these have BPM
KEY_PRECEDENCE = ["beatport", "spotify"]  # Only these have key
GENRE_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify", "itunes"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport/Qobuz
LABEL_PRECEDENCE = ["beatport", "qobuz", "tidal", "spotify"]
CATALOG_NUMBER_PRECEDENCE = ["beatport", "qobuz"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["qobuz", "tidal", "beatport", "spotify", "itunes"]
ARTIST_PRECEDENCE = ["qobuz", "tidal", "beatport", "spotify", "itunes"]
ALBUM_PRECEDENCE = ["qobuz", "tidal", "beatport", "spotify", "itunes"]

# Artwork - hi-res services first
ARTWORK_PRECEDENCE = ["qobuz", "tidal", "spotify", "beatport", "itunes"]

# Spotify audio features - only Spotify has these
AUDIO_FEATURES_SOURCE = "spotify"
