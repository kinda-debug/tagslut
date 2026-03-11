from __future__ import annotations

from tagslut.dj.spotify_key import spotify_key_to_classical


def test_spotify_key_to_classical_handles_supported_inputs() -> None:
    assert spotify_key_to_classical(0, 1) == "C major"
    assert spotify_key_to_classical(0, 0) == "C minor"
    assert spotify_key_to_classical(3, 1) == "Eb major"
    assert spotify_key_to_classical(3, 0) == "D# minor"
    assert spotify_key_to_classical(8, 1) == "Ab major"
    assert spotify_key_to_classical(8, 0) == "G# minor"
    assert spotify_key_to_classical(10, 1) == "Bb major"
    assert spotify_key_to_classical(10, 0) == "A# minor"
    assert spotify_key_to_classical(9, 1) == "A major"
    assert spotify_key_to_classical(9, 0) == "A minor"


def test_spotify_key_to_classical_returns_none_for_invalid_input() -> None:
    assert spotify_key_to_classical(-1, 0) is None
    assert spotify_key_to_classical(12, 0) is None
    assert spotify_key_to_classical(0, 2) is None
