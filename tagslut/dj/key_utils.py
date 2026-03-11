from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

_VALID_TONICS = {
    "A",
    "A#",
    "Ab",
    "B",
    "Bb",
    "C",
    "C#",
    "D",
    "D#",
    "Db",
    "E",
    "Eb",
    "F",
    "F#",
    "G",
    "G#",
    "Gb",
}

_CLASSICAL_TO_CAMELOT = {
    "C major": "8B",
    "A minor": "8A",
    "G major": "9B",
    "E minor": "9A",
    "D major": "10B",
    "B minor": "10A",
    "A major": "11B",
    "F# minor": "11A",
    "E major": "12B",
    "C# minor": "12A",
    "B major": "1B",
    "G# minor": "1A",
    "F# major": "2B",
    "D# minor": "2A",
    "C# major": "3B",
    "A# minor": "3A",
    "F major": "7B",
    "D minor": "7A",
    "Bb major": "6B",
    "G minor": "6A",
    "Eb major": "5B",
    "C minor": "5A",
    "Ab major": "4B",
    "F minor": "4A",
}

_CAMELOT_TO_CLASSICAL = {
    camelot: classical for classical, camelot in _CLASSICAL_TO_CAMELOT.items()
}

_ENHARMONIC_ALIASES = {
    "A# major": "Bb major",
    "Bb minor": "A# minor",
    "Db major": "C# major",
    "Db minor": "C# minor",
    "D# major": "Eb major",
    "Eb minor": "D# minor",
    "Gb major": "F# major",
    "Gb minor": "F# minor",
    "G# major": "Ab major",
    "Ab minor": "G# minor",
}

_CAMELOT_PATTERN = re.compile(r"^(?:[1-9]|1[0-2])[AB]$")


def normalize_key(raw: str | None) -> str | None:
    """Normalize a provider key string to '<Tonic> <mode>' form."""
    if raw is None:
        return None

    value = raw.strip()
    if not value:
        return None

    parts = value.split()

    if len(parts) == 2 and parts[1].lower() in {"major", "minor"}:
        tonic = _normalize_tonic(parts[0])
        mode = parts[1].lower()
    elif len(parts) == 1:
        token = parts[0]
        if token.lower().endswith("m") and len(token) > 1:
            tonic = _normalize_tonic(token[:-1])
            mode = "minor"
        else:
            tonic = _normalize_tonic(token)
            mode = "major"
    else:
        tonic = None
        mode = ""

    if tonic is None:
        log.warning("Unrecognized key value: %r", raw)
        return None

    return f"{tonic} {mode}"


def classical_to_camelot(key: str | None) -> str | None:
    """Convert a classical key string to Camelot notation."""
    normalized = normalize_key(key)
    if normalized is None:
        return None

    lookup_key = _ENHARMONIC_ALIASES.get(normalized, normalized)
    return _CLASSICAL_TO_CAMELOT.get(lookup_key)


def camelot_to_classical(camelot: str | None) -> str | None:
    """Convert Camelot notation to a normalized classical key string."""
    if camelot is None:
        return None

    value = camelot.strip().upper()
    if not value or not _CAMELOT_PATTERN.fullmatch(value):
        return None

    return _CAMELOT_TO_CLASSICAL.get(value)


def _normalize_tonic(raw_tonic: str) -> str | None:
    match = re.fullmatch(r"([A-Ga-g])([#bB]?)", raw_tonic.strip())
    if match is None:
        return None

    note = match.group(1).upper()
    accidental = match.group(2)
    if accidental in {"b", "B"}:
        accidental = "b"

    tonic = f"{note}{accidental}"
    if tonic not in _VALID_TONICS:
        return None

    return tonic
