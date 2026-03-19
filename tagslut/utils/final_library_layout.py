from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

EN_DASH = "\u2013"

_TRUTHY = {"1", "true", "yes", "y", "t"}
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
_YEAR_RE = re.compile(r"^(\d{4})")
_INT_RE = re.compile(r"(\d+)")
_AUDIO_EXT_RE = re.compile(r"\.(flac|aiff?|wav|mp3|m4a)$", re.IGNORECASE)


class FinalLibraryLayoutError(ValueError):
    pass


@dataclass(frozen=True)
class FinalLibraryLayoutResult:
    dest_path: Path
    is_various_artists: bool
    albumartist: str
    artist_for_filename: str
    year: str
    album: str
    title: str
    disc_track: str


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    s = str(value).strip()
    return [s] if s else []


def normalize_tags(tags: Mapping[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tag_key, tag_value in tags.items():
        out[str(tag_key).lower()] = _as_str_list(tag_value)
    return out


def first_tag(tags: Mapping[str, list[str]], keys: Sequence[str]) -> str:
    for tag_key in keys:
        vals = tags.get(tag_key.lower()) or []
        if vals:
            tag_value = str(vals[0]).strip()
            if tag_value:
                return tag_value
    return ""


def _parse_int(value: str) -> int | None:
    if not value:
        return None
    head = value.split("/", 1)[0].strip()
    int_match = _INT_RE.search(head)
    if not int_match:
        return None
    try:
        return int(int_match.group(1))
    except ValueError:
        return None


def _extract_year_from_text(value: str) -> str | None:
    if not value:
        return None
    year_match = _YEAR_RE.match(value.strip())
    return year_match.group(1) if year_match else None


def sanitize_component(value: str) -> str:
    sanitized = unicodedata.normalize("NFC", (value or "").strip())
    sanitized = _CTRL_CHARS_RE.sub(" ", sanitized)
    sanitized = re.sub(r"[\\/]+", " - ", sanitized)
    sanitized = re.sub(r"[:*?\"<>|]", "", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    # Avoid trailing spaces/periods (Windows + FAT safety).
    sanitized = sanitized.rstrip(" .")
    return sanitized


def strip_square_brackets(value: str) -> str:
    # Deterministic and conservative: remove bracket chars but keep content.
    stripped = value.replace("[", "").replace("]", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", stripped).strip()


def strip_audio_extension(value: str) -> str:
    text = (value or "").strip()
    while True:
        stripped = _AUDIO_EXT_RE.sub("", text).strip()
        if stripped == text:
            return stripped
        text = stripped


def _looks_like_artist_list(value: str, *, min_commas: int = 3) -> bool:
    """
    Heuristic: treat very long comma-separated albumartist strings as "Various Artists".

    We intentionally require multiple commas to avoid misclassifying names like
    "Lastname, Firstname" (1 comma) or common 2-artist collaborations.
    """
    if not value:
        return False
    return value.count(",") >= int(min_commas)


def is_various_artists(tags: Mapping[str, list[str]]) -> bool:
    albumartist = first_tag(tags, ["albumartist", "album artist"])
    if albumartist.strip().lower() in {"various artists", "va", "various"}:
        return True
    if _looks_like_artist_list(albumartist, min_commas=3):
        return True
    compilation = first_tag(tags, ["compilation", "itunescompilation"])
    return compilation.strip().lower() in _TRUTHY


def build_final_library_destination(
    raw_tags: Mapping[str, Any],
    dest_root: Path,
    *,
    year_keys: Sequence[str] = ("date", "originaldate", "year"),
    strip_brackets: bool = True,
    max_component_bytes: int = 240,
) -> FinalLibraryLayoutResult:
    """
    Build the canonical FINAL_LIBRARY destination path from tags.

    Convention:
      {albumartist}/({year}) {album}/{artist_or_albumartist} – ({year}) {album} – {disc}{track} {title}.flac

    Rules:
    - Uses Album Artist for folder and filename, except Various Artists albums where filename uses Track Artist.
    - Uses EN DASH (U+2013) separators and deterministic sanitization for filesystem safety.
    """
    tags = normalize_tags(raw_tags)

    various = is_various_artists(tags)

    albumartist = first_tag(tags, ["albumartist", "album artist"])
    artist = first_tag(tags, ["artist"])
    album = first_tag(tags, ["album"])
    title = first_tag(tags, ["title"])

    year: str | None = None
    for k in year_keys:
        year = _extract_year_from_text(first_tag(tags, [k]))
        if year:
            break

    track_number = _parse_int(first_tag(tags, ["tracknumber", "track"]))
    disc_number = _parse_int(first_tag(tags, ["discnumber", "disc"]))
    total_disc_count = _parse_int(first_tag(tags, ["totaldiscs", "disctotal"]))

    if not album:
        raise FinalLibraryLayoutError("missing required tag: album")
    if not title:
        raise FinalLibraryLayoutError("missing required tag: title")
    if not year:
        raise FinalLibraryLayoutError("missing required tag: date/originaldate/year")
    if track_number is None:
        raise FinalLibraryLayoutError("missing/invalid required tag: tracknumber")

    if various:
        folder_artist_raw = "Various Artists"
        filename_artist_raw = artist
        if not filename_artist_raw:
            raise FinalLibraryLayoutError("various artists release missing required tag: artist")
    else:
        folder_artist_raw = albumartist
        filename_artist_raw = albumartist
        if not albumartist:
            raise FinalLibraryLayoutError("missing required tag: albumartist")

    disc = disc_number if disc_number is not None else 1
    if total_disc_count is not None and total_disc_count > 1 and disc_number is None:
        raise FinalLibraryLayoutError("missing required tag: discnumber (multi-disc)")

    multi_disc = (total_disc_count is not None and total_disc_count > 1) or disc > 1
    disc_track = f"{disc}{track_number:02d}" if multi_disc else f"{track_number:02d}"

    folder_artist = sanitize_component(folder_artist_raw)
    sanitized_album = sanitize_component(album)
    sanitized_title = sanitize_component(title)
    filename_artist = sanitize_component(filename_artist_raw)

    sanitized_title = strip_audio_extension(sanitized_title)
    filename_artist = strip_audio_extension(filename_artist)

    if strip_brackets:
        folder_artist = strip_square_brackets(folder_artist)
        sanitized_album = strip_square_brackets(sanitized_album)
        sanitized_title = strip_square_brackets(sanitized_title)
        filename_artist = strip_square_brackets(filename_artist)

    if not folder_artist:
        raise FinalLibraryLayoutError("albumartist sanitizes to empty")
    if not sanitized_album:
        raise FinalLibraryLayoutError("album sanitizes to empty")
    if not sanitized_title:
        raise FinalLibraryLayoutError("title sanitizes to empty")
    if not filename_artist:
        raise FinalLibraryLayoutError("artist sanitizes to empty")

    album_folder = f"({year}) {sanitized_album}"
    filename = f"{filename_artist} {EN_DASH} ({year}) {sanitized_album} {EN_DASH} {disc_track} {sanitized_title}.flac"

    def _byte_len(component: str) -> int:
        return len(component.encode("utf-8", errors="replace"))

    # Conservative safety gate: avoid filesystem errors on long components.
    if _byte_len(folder_artist) > max_component_bytes:
        raise FinalLibraryLayoutError("path component too long: albumartist")
    if _byte_len(album_folder) > max_component_bytes:
        raise FinalLibraryLayoutError("path component too long: album")
    if _byte_len(filename) > max_component_bytes:
        raise FinalLibraryLayoutError("path component too long: filename")

    dest = dest_root / folder_artist / album_folder / filename
    return FinalLibraryLayoutResult(
        dest_path=dest,
        is_various_artists=various,
        albumartist=folder_artist_raw,
        artist_for_filename=filename_artist_raw,
        year=year,
        album=album,
        title=title,
        disc_track=disc_track,
    )
