This file is designed so you can import it anywhere inside your pipeline:

# picard_path.py
import os

# -------------------------
# Normalization utilities
# -------------------------

def clean_value(v):
    """
    Clean a tag value:
    - Convert list → first element
    - Replace ":" with "꞉"
    - Strip spaces
    """
    if not v:
        return ""
    if isinstance(v, list):
        v = v[0]
    return str(v).replace(":", "꞉").strip()


def safe_artist(tags, fallback="Unknown Artist"):
    return clean_value(tags.get("albumartist") or tags.get("artist") or fallback)


def safe_artist_filename(tags, fallback="X"):
    return clean_value(tags.get("albumartist") or tags.get("artist") or fallback)


def safe_album(tags):
    return clean_value(tags.get("album") or "Unknown Album")


def get_year(tags):
    """
    Picard logic:
    $if2($left(%date%,4),$left(%originalyear%,4),$left(%originaldate%,4),"XXXX")
    """
    for key in ("date", "originalyear", "originaldate"):
        v = tags.get(key)  