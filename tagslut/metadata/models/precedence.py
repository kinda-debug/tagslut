"""Precedence rules for canonical metadata selection."""

# Precedence rules for cascading (best source first)
# Based on data quality and specialization of each service

# Timing - Beatport is gold standard for electronic
DURATION_PRECEDENCE = ["beatport", "tidal", "deezer", "traxsource", "apple_music"]

# DJ metadata - Beatport specializes; Tidal and Traxsource also have key/BPM
BPM_PRECEDENCE = ["beatport", "traxsource", "tidal", "deezer"]
KEY_PRECEDENCE = ["beatport", "traxsource", "tidal"]
GENRE_PRECEDENCE = ["beatport", "traxsource", "tidal", "deezer", "apple_music"]
SUB_GENRE_PRECEDENCE = ["beatport"]  # Only Beatport has sub-genres

# Release info - labels care about Beatport
LABEL_PRECEDENCE = ["beatport", "traxsource", "tidal", "apple_music", "deezer"]
CATALOG_NUMBER_PRECEDENCE = ["beatport"]

# Core identity - prefer services with better catalog data
TITLE_PRECEDENCE = ["tidal", "beatport", "traxsource", "apple_music", "deezer", "musicbrainz"]
ARTIST_PRECEDENCE = ["tidal", "beatport", "traxsource", "apple_music", "deezer", "musicbrainz"]
ALBUM_PRECEDENCE = ["tidal", "beatport", "traxsource", "apple_music", "deezer", "musicbrainz"]

# Artwork - hi-res services first (Apple Music has high-res artwork)
ARTWORK_PRECEDENCE = ["tidal", "apple_music", "deezer", "beatport", "traxsource"]

# Composer - Apple Music has good composer data
COMPOSER_PRECEDENCE = ["apple_music", "tidal"]

# ISRC - all major services have this
ISRC_PRECEDENCE = ["beatport", "tidal", "traxsource", "deezer", "apple_music", "musicbrainz"]

# Spotify audio features - dead since Nov 2024
AUDIO_FEATURES_SOURCE = ""
