from __future__ import annotations

import pytest

from tagslut.enrichment.camelot import to_camelot


@pytest.mark.parametrize(
    ("key", "scale", "expected"),
    [
        ("C", "MAJOR", "8B"),
        ("G", "MAJOR", "9B"),
        ("D", "MAJOR", "10B"),
        ("A", "MAJOR", "11B"),
        ("E", "MAJOR", "12B"),
        ("B", "MAJOR", "1B"),
        ("FSharp", "MAJOR", "2B"),
        ("Db", "MAJOR", "3B"),
        ("Ab", "MAJOR", "4B"),
        ("Eb", "MAJOR", "5B"),
        ("Bb", "MAJOR", "6B"),
        ("F", "MAJOR", "7B"),
        ("A", "MINOR", "8A"),
        ("E", "MINOR", "9A"),
        ("B", "MINOR", "10A"),
        ("FSharp", "MINOR", "11A"),
        ("Db", "MINOR", "12A"),
        ("Ab", "MINOR", "1A"),
        ("Eb", "MINOR", "2A"),
        ("Bb", "MINOR", "3A"),
        ("F", "MINOR", "4A"),
        ("C", "MINOR", "5A"),
        ("G", "MINOR", "6A"),
        ("D", "MINOR", "7A"),
    ],
)
def test_to_camelot_maps_all_24(key: str, scale: str, expected: str) -> None:
    assert to_camelot(key, scale) == expected


def test_to_camelot_enharmonics_match() -> None:
    assert to_camelot("FSharp", "MAJOR") == "2B"
    assert to_camelot("Gb", "MAJOR") == "2B"
    assert to_camelot("CSharp", "MINOR") == "12A"
    assert to_camelot("Db", "MINOR") == "12A"


def test_to_camelot_unknown_returns_none() -> None:
    assert to_camelot("H", "MAJOR") is None
    assert to_camelot("C", "DORIAN") is None

