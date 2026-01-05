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
    Tagger logic:
    $if2($left(%date%,4),$left(%originalyear%,4),$left(%originaldate%,4),"XXXX")
    """
    for key in ("date", "originalyear", "originaldate"):
        v = tags.get(key)
        if v:
            v = clean_value(v)
            if v:
                return v[:4]
    return "XXXX"


def safe_disc(tags):
    total = int(tags.get("totaldiscs") or 1)
    disc = int(tags.get("discnumber") or 0)
    prefix = f"{disc:02d}-" if total > 1 else ""
    return prefix


def safe_track(tags):
    """
    $num(%tracknumber%,2)
    """
    try:
        return f"{int(tags.get('tracknumber') or 0):02d}"
    except Exception:
        return "00"


def safe_title(tags):
    return clean_value(tags.get("title") or "Unknown Title")


# -------------------------
# Canonical tagger path
# -------------------------

def build_picard_path(tags):
    """
    Full tagger-style canonical path generator used for 20_ACCEPTED.
    Mirrors your EXACT naming formula.
    """

    top_dir = safe_artist(tags) or "Unknown Artist"
    album = safe_album(tags)
    year = get_year(tags)

    folder = f"{year} {album}"

    artist = safe_artist_filename(tags)
    disc_prefix = safe_disc(tags)
    track = safe_track(tags)
    title = safe_title(tags)

    filename = f"{artist} - {year} {album} - {disc_prefix}{track}. {title}.flac"

    return os.path.join(top_dir, folder, filename)
