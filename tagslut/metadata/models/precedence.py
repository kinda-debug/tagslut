"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic
DURATION_PRECEDENCE = ["beatport", "tidal"]

# DJ metadata - Beatport specializes; Tidal also has key/BPM
BPM_PRECEDENCE = ["beatport", "tidal"]
KEY_PRECEDENCE = ["beatport", "tidal"]
GENRE_PRECEDENCE = ["beatport", "tidal"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport
LABEL_PRECEDENCE = ["beatport", "tidal"]
CATALOG_NUMBER_PRECEDENCE = ["beatport"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["tidal", "beatport"]
ARTIST_PRECEDENCE = ["tidal", "beatport"]
ALBUM_PRECEDENCE = ["tidal", "beatport"]

# Artwork
ARTWORK_PRECEDENCE = ["tidal", "beatport"]

# Composer - Tidal has composer data
COMPOSER_PRECEDENCE = ["tidal"]

# ISRC
ISRC_PRECEDENCE = ["beatport", "tidal"]

# Spotify audio features - dead since Nov 2024
AUDIO_FEATURES_SOURCE = ""
