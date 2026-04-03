from __future__ import annotations


def _normalize_scale(scale: str) -> str | None:
    text = (scale or "").strip().lower()
    if text in {"major", "maj"}:
        return "major"
    if text in {"minor", "min"}:
        return "minor"
    return None


def _normalize_key(key: str) -> str | None:
    text = (key or "").strip()
    if not text:
        return None
    text = text.replace("♯", "#").replace("♭", "b")
    text = text.replace(" ", "").replace("_", "").replace("-", "")
    text = text.lower()

    aliases: dict[str, str] = {
        "c": "c",
        "g": "g",
        "d": "d",
        "a": "a",
        "e": "e",
        "b": "b",
        "f": "f",
        "f#": "fsharp",
        "fsharp": "fsharp",
        "gb": "gb",
        "gflat": "gb",
        "db": "db",
        "dflat": "db",
        "c#": "csharp",
        "csharp": "csharp",
        "ab": "ab",
        "aflat": "ab",
        "g#": "gsharp",
        "gsharp": "gsharp",
        "eb": "eb",
        "eflat": "eb",
        "d#": "dsharp",
        "dsharp": "dsharp",
        "bb": "bb",
        "bflat": "bb",
        "a#": "asharp",
        "asharp": "asharp",
    }
    return aliases.get(text)


_CAMELOT: dict[tuple[str, str], str] = {
    # Major = B
    ("c", "major"): "8B",
    ("g", "major"): "9B",
    ("d", "major"): "10B",
    ("a", "major"): "11B",
    ("e", "major"): "12B",
    ("b", "major"): "1B",
    ("fsharp", "major"): "2B",
    ("gb", "major"): "2B",
    ("db", "major"): "3B",
    ("csharp", "major"): "3B",
    ("ab", "major"): "4B",
    ("gsharp", "major"): "4B",
    ("eb", "major"): "5B",
    ("dsharp", "major"): "5B",
    ("bb", "major"): "6B",
    ("asharp", "major"): "6B",
    ("f", "major"): "7B",
    # Minor = A
    ("a", "minor"): "8A",
    ("e", "minor"): "9A",
    ("b", "minor"): "10A",
    ("fsharp", "minor"): "11A",
    ("gb", "minor"): "11A",
    ("db", "minor"): "12A",
    ("csharp", "minor"): "12A",
    ("ab", "minor"): "1A",
    ("gsharp", "minor"): "1A",
    ("eb", "minor"): "2A",
    ("dsharp", "minor"): "2A",
    ("bb", "minor"): "3A",
    ("asharp", "minor"): "3A",
    ("f", "minor"): "4A",
    ("c", "minor"): "5A",
    ("g", "minor"): "6A",
    ("d", "minor"): "7A",
}


def to_camelot(key: str, scale: str) -> str | None:
    """
    Convert TIDAL key/keyScale to Camelot notation.
    Case-insensitive normalization for key + scale.
    Returns None for unknown inputs without raising.
    """
    norm_key = _normalize_key(key)
    norm_scale = _normalize_scale(scale)
    if norm_key is None or norm_scale is None:
        return None
    return _CAMELOT.get((norm_key, norm_scale))

