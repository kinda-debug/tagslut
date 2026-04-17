"""
Source-audio to MP3 transcoder for DJ pool export.

Master source files are NEVER modified. MP3 is written to dest_dir.
DJ copies intentionally keep only a small, operational tag set plus artwork.
Requires ffmpeg installed as a system dependency.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, cast

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Cover

from tagslut.exec.dj_tag_snapshot import DjTagSnapshot

logger = logging.getLogger(__name__)

# Common source tags already mapped to explicit ID3 frames in _apply_full_id3_tags.
# Any remaining source tag NOT in this set is treated as a credit role and written as TXXX.
_FULL_TAG_STANDARD_KEYS: frozenset[str] = frozenset({
    "title", "artist", "albumartist", "album", "tracknumber", "discnumber",
    "date", "originaldate", "year", "genre", "bpm", "initialkey", "key",
    "isrc", "label", "copyright", "lyrics", "comment", "composer",
})

DJ_MANAGED_FRAMES = (
    "TIT2",
    "TPE1",
    "TALB",
    "TDRC",
    "TCON",
    "TBPM",
    "TKEY",
    "TSRC",
    "TXXX:INITIALKEY",
    "TXXX:LABEL",
    "TXXX:ENERGY",
    "USLT",
    "SYLT",
    "APIC",
)


class TranscodeError(Exception):
    pass


class FFmpegNotFoundError(TranscodeError):
    pass


TagLookup = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class SourceTagData:
    tags: dict[str, list[str]]
    cover_art: tuple[bytes, str] | None = None

    def first(self, key: str) -> str | None:
        values = self.tags.get(key.lower())
        if not values:
            return None
        value = str(values[0]).strip()
        return value or None


def _mutagen_id3() -> Any:
    from mutagen import id3 as mutagen_id3

    return mutagen_id3


def _check_ffmpeg(ffmpeg_path: str | None = None) -> None:
    if ffmpeg_path:
        resolved = shutil.which(ffmpeg_path) or (ffmpeg_path if Path(ffmpeg_path).exists() else None)
        if resolved is not None:
            return
    if shutil.which("ffmpeg") is None:
        raise FFmpegNotFoundError(
            "ffmpeg not found in PATH. Install it: brew install ffmpeg (macOS) "
            "or apt install ffmpeg (Linux)"
        )


def _normalize_tag_values(value: Any) -> list[str]:
    if value is None:
        return []
    if hasattr(value, "text"):
        return _normalize_tag_values(getattr(value, "text"))
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_normalize_tag_values(item))
        return [item for item in out if item]
    if isinstance(value, bytes):
        for encoding in ("utf-8", "latin-1"):
            with contextlib.suppress(Exception):
                text = value.decode(encoding).strip()
                if text:
                    return [text]
        return []
    text = str(value).strip()
    return [text] if text else []


def _normalize_tag_mapping(tags: Any) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    if tags is None:
        return normalized
    try:
        items = tags.items()
    except Exception:
        return normalized
    for key, value in items:
        values = _normalize_tag_values(value)
        if values:
            normalized[str(key).strip().lower()] = values
    return normalized


def _first_raw_tag(tags: Any, *keys: str) -> str | None:
    if tags is None:
        return None
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        values = _normalize_tag_values(value)
        if values:
            return values[0]
    return None


def _extract_cover_art(audio: Any) -> tuple[bytes, str] | None:
    pictures = getattr(audio, "pictures", None) or []
    if pictures:
        front_cover = None
        for picture in pictures:
            if getattr(picture, "type", None) == 3:
                front_cover = picture
                break
        if front_cover is None:
            front_cover = pictures[0]
        data = getattr(front_cover, "data", None)
        if data:
            mime = getattr(front_cover, "mime", None) or "image/jpeg"
            return bytes(data), str(mime)

    tags = getattr(audio, "tags", None)
    if tags is None:
        return None

    try:
        apic_frames = tags.getall("APIC")
    except Exception:
        apic_frames = []
    if apic_frames:
        frame = apic_frames[0]
        data = getattr(frame, "data", None)
        if data:
            mime = getattr(frame, "mime", None) or "image/jpeg"
            return bytes(data), str(mime)

    try:
        covr_frames = tags.get("covr")
    except Exception:
        covr_frames = None
    if covr_frames:
        frame = covr_frames[0]
        data = bytes(frame)
        imageformat = getattr(frame, "imageformat", None)
        mime = "image/png" if imageformat == getattr(MP4Cover, "FORMAT_PNG", 14) else "image/jpeg"
        return data, mime

    return None


def _load_source_metadata(source: Path) -> SourceTagData | None:
    suffix = source.suffix.lower()
    try:
        if suffix == ".flac":
            audio: Any = FLAC(source)
            tags = _normalize_tag_mapping(getattr(audio, "tags", None))
            return SourceTagData(tags=tags, cover_art=_extract_cover_art(audio))

        easy_audio = MutagenFile(str(source), easy=True)
        raw_audio = None
        with contextlib.suppress(Exception):
            raw_audio = MutagenFile(str(source), easy=False)

        tags: dict[str, list[str]] = {}
        if easy_audio is not None:
            tags = _normalize_tag_mapping(getattr(easy_audio, "tags", None))

        if not tags and raw_audio is not None:
            tags = _normalize_tag_mapping(getattr(raw_audio, "tags", None))

        if suffix in {".m4a", ".mp4"} and raw_audio is not None:
            raw_tags = getattr(raw_audio, "tags", None)
            if raw_tags is not None:
                extras = {
                    "isrc": _first_raw_tag(raw_tags, "----:com.apple.iTunes:ISRC", "ISRC"),
                    "comment": _first_raw_tag(raw_tags, "\xa9cmt"),
                    "lyrics": _first_raw_tag(raw_tags, "\xa9lyr"),
                    "composer": _first_raw_tag(raw_tags, "\xa9wrt"),
                    "label": _first_raw_tag(raw_tags, "----:com.apple.iTunes:LABEL"),
                    "initialkey": _first_raw_tag(raw_tags, "----:com.apple.iTunes:INITIALKEY"),
                }
                for key, value in extras.items():
                    if value and key not in tags:
                        tags[key] = [value]

        return SourceTagData(tags=tags, cover_art=_extract_cover_art(raw_audio or easy_audio))
    except Exception as exc:
        logger.warning("Could not read source tags from %s: %s", source, exc)
        return None


def _build_mp3_filename(source: Path, tags: Optional[SourceTagData]) -> str:
    """
    Build DJ-friendly MP3 filename: Artist - Title (Key) (BPM).mp3
    Falls back to source stem if tags are missing.
    """
    if tags is None:
        return source.stem + ".mp3"

    artist = tags.first("artist") or tags.first("albumartist") or ""
    title = tags.first("title") or ""
    key = tags.first("initialkey") or tags.first("key") or ""
    bpm = tags.first("bpm") or ""

    if not artist or not title:
        return source.stem + ".mp3"

    parts = f"{artist} - {title}"
    if key:
        parts += f" ({key})"
    if bpm:
        parts += f" ({bpm})"

    safe = "".join(c for c in parts if c not in r'\\/:*?"<>|')
    return safe + ".mp3"


def _build_snapshot_mp3_filename(
    source: Path,
    snapshot: DjTagSnapshot,
    *,
    include_identity_id: bool = False,
) -> str:
    artist = (snapshot.artist or "").strip()
    title = (snapshot.title or "").strip()
    bpm = (snapshot.bpm or "").strip()
    key = (snapshot.musical_key or "").strip()

    if not artist or not title:
        raise TranscodeError(f"missing artist/title for DJ snapshot export: {source}")

    parts = f"{artist} - {title}"
    if include_identity_id and snapshot.identity_id is not None:
        parts += f" [{snapshot.identity_id}]"
    if key:
        parts += f" ({key})"
    if bpm:
        parts += f" ({bpm})"
    safe = "".join(c for c in parts if c not in r'\\/:*?"<>|')
    return safe + ".mp3"


def _snapshot_with_flac_fallback(snapshot: DjTagSnapshot, source_tags: Optional[SourceTagData]) -> DjTagSnapshot:
    if source_tags is None:
        return snapshot

    artist = snapshot.artist or source_tags.first("artist") or source_tags.first("albumartist")
    title = snapshot.title or source_tags.first("title")
    album = snapshot.album or source_tags.first("album")
    year_text = (
        str(snapshot.year) if snapshot.year is not None else (
            source_tags.first("date") or source_tags.first("originaldate") or source_tags.first("year")
        )
    )
    year: int | None = snapshot.year
    if year is None and year_text:
        try:
            year = int(str(year_text).split("-", 1)[0].split(";", 1)[0].strip())
        except ValueError:
            year = None

    return DjTagSnapshot(
        artist=artist,
        title=title,
        album=album,
        genre=snapshot.genre or source_tags.first("genre"),
        label=snapshot.label or source_tags.first("label"),
        year=year,
        isrc=snapshot.isrc or source_tags.first("isrc"),
        bpm=snapshot.bpm or source_tags.first("bpm"),
        musical_key=snapshot.musical_key or source_tags.first("initialkey") or source_tags.first("key"),
        energy_1_10=snapshot.energy_1_10,
        bpm_source=snapshot.bpm_source,
        key_source=snapshot.key_source,
        energy_source=snapshot.energy_source,
        identity_id=snapshot.identity_id,
        preferred_asset_id=snapshot.preferred_asset_id,
        preferred_path=snapshot.preferred_path,
    )


def transcode_to_mp3(
    source: Path,
    dest_dir: Path,
    bitrate: int = 320,
    overwrite: bool = False,
) -> Path:
    """
    Transcode a source audio file to MP3 and copy to dest_dir.

    The source file is never modified.
    Tags are copied from the source to MP3 via mutagen.

    Args:
        source:    Absolute path to the source audio file.
        dest_dir:  Destination directory for the MP3.
        bitrate:   MP3 bitrate in kbps (default 320).
        overwrite: If False, skip if dest already exists.

    Returns:
        Path to the created MP3 file.

    Raises:
        FFmpegNotFoundError: If ffmpeg is not installed.
        TranscodeError: If ffmpeg returns a non-zero exit code.
        FileNotFoundError: If source does not exist.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    _check_ffmpeg()

    source_tags = _load_source_metadata(source)

    dest_dir.mkdir(parents=True, exist_ok=True)
    mp3_name = _build_mp3_filename(source, source_tags)
    dest_path = dest_dir / mp3_name

    if dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", dest_path)
        return dest_path

    _run_ffmpeg_transcode(source, dest_path, bitrate=bitrate, ffmpeg_path=None)
    _apply_id3_tags(dest_path, source_tags, prune_existing=True)

    logger.info("Transcoded: %s -> %s", source, dest_path)
    return dest_path


def build_dj_copy_filename(source_flac: Path) -> str:
    """Return the DJ-copy filename for a source file (no I/O besides tag read)."""
    source_tags = _load_source_metadata(source_flac)
    return _build_mp3_filename(source_flac, source_tags)


def tag_mp3_as_dj_copy(mp3_path: Path, source_flac: Path) -> None:
    """Apply the DJ tag policy to an existing MP3, pruning to the DJ-managed frames."""
    source_tags = _load_source_metadata(source_flac)
    _apply_id3_tags(mp3_path, source_tags, prune_existing=True)


def transcode_to_mp3_from_snapshot(
    source: Path,
    dest_dir: Path,
    snapshot: DjTagSnapshot,
    *,
    bitrate: int = 320,
    overwrite: bool = False,
    ffmpeg_path: str | None = None,
    dest_path: Path | None = None,
) -> Path:
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    _check_ffmpeg(ffmpeg_path)

    source_tags = _load_source_metadata(source)

    resolved_snapshot = _snapshot_with_flac_fallback(snapshot, source_tags)
    if not resolved_snapshot.artist or not resolved_snapshot.title:
        raise TranscodeError(f"DJ snapshot export requires artist/title metadata: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final_dest_path = dest_path or (dest_dir / _build_snapshot_mp3_filename(source, resolved_snapshot))

    final_dest_path.parent.mkdir(parents=True, exist_ok=True)

    if final_dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", final_dest_path)
        return final_dest_path

    _run_ffmpeg_transcode(source, final_dest_path, bitrate=bitrate, ffmpeg_path=ffmpeg_path)
    _apply_snapshot_id3_tags(final_dest_path, resolved_snapshot, source_tags, prune_existing=True)

    logger.info("Transcoded from snapshot: %s -> %s", source, final_dest_path)
    return final_dest_path


def transcode_to_mp3_full_tags(
    source: Path,
    dest_path: Path,
    *,
    bitrate: int = 320,
    overwrite: bool = False,
    ffmpeg_path: str | None = None,
) -> Path:
    """Transcode a source audio file to MP3 and apply a broader, library-friendly tag set."""
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    _check_ffmpeg(ffmpeg_path)

    source_tags = _load_source_metadata(source)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", dest_path)
        return dest_path

    _run_ffmpeg_transcode(source, dest_path, bitrate=bitrate, ffmpeg_path=ffmpeg_path)
    _apply_full_id3_tags(dest_path, source_tags)
    logger.info("Transcoded (full tags): %s -> %s", source, dest_path)
    return dest_path


def _run_ffmpeg_transcode(
    source: Path,
    dest_path: Path,
    *,
    bitrate: int,
    ffmpeg_path: str | None,
    validate_output: bool = True,
) -> None:
    cmd = [
        ffmpeg_path or "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate}k",
        "-id3v2_version",
        "3",
        "-map_metadata",
        "-1",
        str(dest_path),
    ]
    logger.debug("Transcoding: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TranscodeError(
            f"ffmpeg failed for {source}:\n{result.stderr[-500:]}"
        )
    if validate_output:
        _validate_mp3_output(dest_path)


def sync_dj_mp3_from_flac(mp3_path: Path, source_flac: Path) -> None:
    """Refresh DJ MP3 tags/artwork from an enriched source file."""
    source_tags = _load_source_metadata(source_flac)
    _apply_id3_tags(mp3_path, source_tags, prune_existing=False)


def _validate_mp3_output(path: Path, *, min_size_bytes: int = 4096) -> None:
    """Validate that a transcoded MP3 is playable and has readable ID3 tags.

    Raises TranscodeError on any validation failure so callers can treat the
    file as failed rather than silently accepting a corrupt output.

    Checks:
    1. File exists and is not empty.
    2. File size >= min_size_bytes (default 4KB — filters truncated writes).
    3. mutagen can parse the file as an MP3 (catches codec/container errors).
    4. Parsed duration > 1.0 seconds (filters silent/near-empty transcodes).
    """
    if not path.exists():
        raise TranscodeError(f"transcode output missing: {path}")
    size = path.stat().st_size
    if size < min_size_bytes:
        raise TranscodeError(
            f"transcode output suspiciously small ({size} bytes): {path}"
        )
    try:
        from mutagen.mp3 import MP3
        audio = MP3(str(path))
        duration = audio.info.length if audio.info else 0.0
    except Exception as exc:
        raise TranscodeError(f"transcode output unreadable by mutagen: {path}: {exc}") from exc
    if duration < 1.0:
        raise TranscodeError(
            f"transcode output duration too short ({duration:.2f}s): {path}"
        )


def _empty_id3() -> ID3:
    return cast(ID3, _mutagen_id3().ID3())


def _load_id3(mp3_path: Path) -> ID3:
    return cast(ID3, _mutagen_id3().ID3(mp3_path))


def _id3_delall(tags: ID3, frame_id: str) -> None:
    cast(Any, tags).delall(frame_id)


def _id3_add(tags: ID3, frame: object) -> None:
    cast(Any, tags).add(frame)


def _apic_frame(data: bytes, mime: str) -> object:
    return _mutagen_id3().APIC(
        encoding=3,
        mime=mime,
        type=3,
        desc="Cover",
        data=data,
    )


def _text_frame(frame_name: str, text: str) -> object:
    return getattr(_mutagen_id3(), frame_name)(encoding=3, text=text)


def _user_text_frame(desc: str, text: str) -> object:
    return _mutagen_id3().TXXX(encoding=3, desc=desc, text=text)


def _apply_id3_tags(
    mp3_path: Path,
    source_tags: Optional[SourceTagData],
    *,
    prune_existing: bool,
) -> None:
    """Apply the DJ tag policy to an MP3 via mutagen ID3."""
    if prune_existing:
        tags = _empty_id3()
    else:
        try:
            tags = _load_id3(mp3_path)
        except Exception as e:
            logger.warning("Could not load existing ID3 tags from %s: %s", mp3_path, e)
            tags = _empty_id3()

    _clear_dj_managed_frames(tags)
    if source_tags is None:
        tags.save(mp3_path)
        return

    def first(key: str) -> Optional[str]:
        return source_tags.first(key)

    _apply_dj_tag_policy(tags, source_tags, first)
    tags.save(mp3_path)


def _apply_full_id3_tags(mp3_path: Path, source_tags: Optional[SourceTagData]) -> None:
    tags = _empty_id3()
    if source_tags is None:
        tags.save(mp3_path)
        return

    def first(key: str) -> Optional[str]:
        return source_tags.first(key)

    title = first("title")
    artist = first("artist") or first("albumartist")
    albumartist = first("albumartist")
    album = first("album")
    tracknumber = first("tracknumber")
    discnumber = first("discnumber")
    date = first("date") or first("originaldate") or first("year")
    genre = first("genre")
    bpm = first("bpm")
    initialkey = first("initialkey") or first("key")
    isrc = first("isrc")
    label = first("label")

    if title:
        tags["TIT2"] = _text_frame("TIT2", title)
    if artist:
        tags["TPE1"] = _text_frame("TPE1", artist)
    if albumartist:
        tags["TPE2"] = _text_frame("TPE2", albumartist)
    if album:
        tags["TALB"] = _text_frame("TALB", album)
    if tracknumber:
        tags["TRCK"] = _text_frame("TRCK", tracknumber)
    if discnumber:
        tags["TPOS"] = _text_frame("TPOS", discnumber)
    if date:
        tags["TDRC"] = _text_frame("TDRC", date)
    if genre:
        tags["TCON"] = _text_frame("TCON", genre)
    if bpm:
        tags["TBPM"] = _text_frame("TBPM", bpm)
    if initialkey:
        tags["TKEY"] = _text_frame("TKEY", initialkey)
        tags["TXXX:INITIALKEY"] = _user_text_frame("INITIALKEY", initialkey)
    if isrc:
        tags["TSRC"] = _text_frame("TSRC", isrc)
    if label:
        tags["TXXX:LABEL"] = _user_text_frame("LABEL", label)

    copyright_val = first("copyright")
    if copyright_val:
        tags["TCOP"] = _text_frame("TCOP", copyright_val)

    composer = first("composer")
    if composer:
        tags["TCOM"] = _text_frame("TCOM", composer)

    lyrics = first("lyrics")
    if lyrics:
        _id3_add(tags, _mutagen_id3().USLT(encoding=3, lang="eng", desc="", text=lyrics))

    comment = first("comment")
    if comment:
        _id3_add(tags, _mutagen_id3().COMM(encoding=3, lang="eng", desc="", text=comment))

    # Write any remaining FLAC keys (e.g. tiddl credit roles: PRODUCER, MIXER,
    # REMIXER, ENGINEER, LYRICIST, …) as TXXX frames.
    for flac_key in source_tags.tags.keys():
        if flac_key.lower() in _FULL_TAG_STANDARD_KEYS:
            continue
        vals = source_tags.tags.get(flac_key)
        if vals:
            value = "; ".join(str(v) for v in vals if str(v).strip())
            if value:
                tags[f"TXXX:{flac_key.upper()}"] = _user_text_frame(flac_key.upper(), value)

    _apply_cover_art(tags, source_tags)
    tags.save(mp3_path)


def _apply_snapshot_id3_tags(
    mp3_path: Path,
    snapshot: DjTagSnapshot,
    source_tags: Optional[SourceTagData],
    *,
    prune_existing: bool,
) -> None:
    if prune_existing:
        tags = _empty_id3()
    else:
        try:
            tags = _load_id3(mp3_path)
        except Exception as e:
            logger.warning("Could not load existing ID3 tags from %s: %s", mp3_path, e)
            tags = _empty_id3()

    _clear_dj_managed_frames(tags)
    _apply_snapshot_tag_policy(tags, snapshot)
    if source_tags is not None:
        _apply_cover_art(tags, source_tags)
    tags.save(mp3_path)


def _clear_dj_managed_frames(tags: ID3) -> None:
    for frame_id in DJ_MANAGED_FRAMES:
        _id3_delall(tags, frame_id)


def _apply_dj_tag_policy(tags: ID3, source_tags: SourceTagData, first: TagLookup) -> None:
    title = first("title")
    artist = first("artist")
    albumartist = first("albumartist")
    album = first("album")
    date = first("date")
    year = first("year")
    genre = first("genre")
    bpm = first("bpm")
    initialkey = first("initialkey")
    key = first("key")
    isrc = first("isrc")
    label = first("label")
    energy = first("energy")

    if title:
        tags["TIT2"] = _text_frame("TIT2", title)
    if artist or albumartist:
        tags["TPE1"] = _text_frame("TPE1", artist or albumartist or "")
    if album:
        tags["TALB"] = _text_frame("TALB", album)
    if date or year:
        tags["TDRC"] = _text_frame("TDRC", date or year or "")
    if genre:
        tags["TCON"] = _text_frame("TCON", genre)
    if bpm:
        tags["TBPM"] = _text_frame("TBPM", bpm)
    if initialkey or key:
        key_value = initialkey or key or ""
        tags["TKEY"] = _text_frame("TKEY", key_value)
        tags["TXXX:INITIALKEY"] = _user_text_frame("INITIALKEY", key_value)
    if isrc:
        tags["TSRC"] = _text_frame("TSRC", isrc)
    if label:
        tags["TXXX:LABEL"] = _user_text_frame("LABEL", label)
    if energy:
        tags["TXXX:ENERGY"] = _user_text_frame("ENERGY", energy)

    _apply_cover_art(tags, source_tags)


def _apply_snapshot_tag_policy(tags: ID3, snapshot: DjTagSnapshot) -> None:
    if snapshot.title:
        tags["TIT2"] = _text_frame("TIT2", snapshot.title)
    if snapshot.artist:
        tags["TPE1"] = _text_frame("TPE1", snapshot.artist)
    if snapshot.album:
        tags["TALB"] = _text_frame("TALB", snapshot.album)
    if snapshot.year is not None:
        tags["TDRC"] = _text_frame("TDRC", str(snapshot.year))
    if snapshot.genre:
        tags["TCON"] = _text_frame("TCON", snapshot.genre)
    if snapshot.bpm:
        tags["TBPM"] = _text_frame("TBPM", snapshot.bpm)
    if snapshot.musical_key:
        tags["TKEY"] = _text_frame("TKEY", snapshot.musical_key)
        tags["TXXX:INITIALKEY"] = _user_text_frame("INITIALKEY", snapshot.musical_key)
    if snapshot.isrc:
        tags["TSRC"] = _text_frame("TSRC", snapshot.isrc)
    if snapshot.label:
        tags["TXXX:LABEL"] = _user_text_frame("LABEL", snapshot.label)
    if snapshot.energy_1_10 is not None:
        tags["TXXX:ENERGY"] = _user_text_frame("ENERGY", str(snapshot.energy_1_10))


def _apply_cover_art(tags: ID3, source_tags: Optional[SourceTagData]) -> None:
    if source_tags is None or source_tags.cover_art is None:
        return
    data, mime = source_tags.cover_art
    if not data:
        return
    _id3_delall(tags, "APIC")
    _id3_add(tags, _apic_frame(data, mime or "image/jpeg"))
