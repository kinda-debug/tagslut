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
