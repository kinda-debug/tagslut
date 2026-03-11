from __future__ import annotations

from tagslut.dj.key_utils import camelot_to_classical
from tagslut.dj.key_utils import classical_to_camelot
from tagslut.dj.key_utils import normalize_key


def test_normalize_key_handles_supported_inputs() -> None:
    assert normalize_key("Am") == "A minor"
    assert normalize_key("F#m") == "F# minor"
    assert normalize_key("Bbm") == "Bb minor"
    assert normalize_key("F#") == "F# major"
    assert normalize_key("Bb") == "Bb major"
    assert normalize_key("A minor") == "A minor"
    assert normalize_key("F# Minor") == "F# minor"
    assert normalize_key("c major") == "C major"


def test_normalize_key_returns_none_for_missing_or_invalid_input() -> None:
    assert normalize_key(None) is None
    assert normalize_key("") is None
    assert normalize_key("xyz_garbage") is None


def test_classical_to_camelot_handles_supported_inputs() -> None:
    assert classical_to_camelot("C minor") == "5A"
    assert classical_to_camelot("F# major") == "2B"
    assert classical_to_camelot("Am") == "8A"


def test_classical_to_camelot_resolves_enharmonic_aliases() -> None:
    assert classical_to_camelot("Bbm") == "3A"
    assert classical_to_camelot("Db") == "3B"


def test_classical_to_camelot_returns_none_for_missing_or_invalid_input() -> None:
    assert classical_to_camelot(None) is None
    assert classical_to_camelot("garbage") is None


def test_camelot_to_classical_handles_supported_inputs() -> None:
    assert camelot_to_classical("5A") == "C minor"
    assert camelot_to_classical("8B") == "C major"
    assert camelot_to_classical("5a") == "C minor"


def test_camelot_to_classical_returns_none_for_missing_or_invalid_input() -> None:
    assert camelot_to_classical(None) is None
    assert camelot_to_classical("13X") is None
