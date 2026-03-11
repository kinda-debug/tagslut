from __future__ import annotations

_MAJOR_TONICS = {
    0: "C",
    1: "C#",
    2: "D",
    3: "Eb",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "Ab",
    9: "A",
    10: "Bb",
    11: "B",
}

_MINOR_TONICS = {
    0: "C",
    1: "C#",
    2: "D",
    3: "D#",
    4: "E",
    5: "F",
    6: "F#",
    7: "G",
    8: "G#",
    9: "A",
    10: "A#",
    11: "B",
}


def spotify_key_to_classical(pitch_class: int, mode: int) -> str | None:
    """Convert Spotify pitch class and mode to classical notation."""
    if mode == 1:
        tonic = _MAJOR_TONICS.get(pitch_class)
        quality = "major"
    elif mode == 0:
        tonic = _MINOR_TONICS.get(pitch_class)
        quality = "minor"
    else:
        return None

    if tonic is None:
        return None

    return f"{tonic} {quality}"


def test_spotify_key_to_classical_valid_major() -> None:
    """Verify all valid pitch classes (0-11) map to the correct major keys."""
    for pitch_class, tonic in _MAJOR_TONICS.items():
        result = spotify_key_to_classical(pitch_class, 1)
        assert result == f"{tonic} major"


def test_spotify_key_to_classical_valid_minor() -> None:
    """Verify all valid pitch classes (0-11) map to the correct minor keys."""
    for pitch_class, tonic in _MINOR_TONICS.items():
        result = spotify_key_to_classical(pitch_class, 0)
        assert result == f"{tonic} minor"


def test_spotify_key_to_classical_invalid_pitch_classes() -> None:
    """Verify invalid pitch classes return None for both major and minor modes."""
    for invalid_pitch_class in (-1, 12):
        assert spotify_key_to_classical(invalid_pitch_class, 1) is None
        assert spotify_key_to_classical(invalid_pitch_class, 0) is None


def test_spotify_key_to_classical_invalid_modes_and_none_handling() -> None:
    """Verify invalid modes and None inputs are handled gracefully."""
    # Invalid modes for a valid pitch class
    for invalid_mode in (2, -1):
        assert spotify_key_to_classical(0, invalid_mode) is None

    # None handling for pitch_class and mode
    assert spotify_key_to_classical(None, 1) is None  # type: ignore[arg-type]
    assert spotify_key_to_classical(0, None) is None  # type: ignore[arg-type]
    assert spotify_key_to_classical(None, None) is None  # type: ignore[arg-type]
