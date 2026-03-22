"""
FLAC to MP3 transcoder for DJ pool export.

Master FLAC files are NEVER modified. MP3 is written to dest_dir.
DJ copies intentionally keep only a small, operational tag set plus artwork.
Requires ffmpeg installed as a system dependency.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional, cast

from mutagen.flac import FLAC
from mutagen.id3 import ID3

from tagslut.exec.dj_tag_snapshot import DjTagSnapshot

logger = logging.getLogger(__name__)

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


def _build_mp3_filename(source: Path, tags: Optional[FLAC]) -> str:
    """
    Build DJ-friendly MP3 filename: Artist - Title (Key) (BPM).mp3
    Falls back to source stem if tags are missing.
    """
    if tags is None:
        return source.stem + ".mp3"

    artist = (tags.get("artist") or tags.get("albumartist") or [""])[0]
    title = (tags.get("title") or [""])[0]
    key = (tags.get("initialkey") or tags.get("key") or [""])[0]
    bpm = (tags.get("bpm") or [""])[0]

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


def _flac_first(flac_tags: Optional[FLAC], key: str) -> str | None:
    if flac_tags is None:
        return None
    values = flac_tags.get(key)
    if not values:
        return None
    value = str(values[0]).strip()
    return value or None


def _snapshot_with_flac_fallback(snapshot: DjTagSnapshot, flac_tags: Optional[FLAC]) -> DjTagSnapshot:
    if flac_tags is None:
        return snapshot

    artist = snapshot.artist or _flac_first(flac_tags, "artist") or _flac_first(flac_tags, "albumartist")
    title = snapshot.title or _flac_first(flac_tags, "title")
    album = snapshot.album or _flac_first(flac_tags, "album")
    year_text = (
        str(snapshot.year) if snapshot.year is not None else (
            _flac_first(flac_tags, "date") or _flac_first(flac_tags, "originaldate") or _flac_first(flac_tags, "year")
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
        genre=snapshot.genre or _flac_first(flac_tags, "genre"),
        label=snapshot.label or _flac_first(flac_tags, "label"),
        year=year,
        isrc=snapshot.isrc or _flac_first(flac_tags, "isrc"),
        bpm=snapshot.bpm or _flac_first(flac_tags, "bpm"),
        musical_key=snapshot.musical_key or _flac_first(flac_tags, "initialkey") or _flac_first(flac_tags, "key"),
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
    Transcode a FLAC file to MP3 and copy to dest_dir.

    The source FLAC is never modified.
    Tags are copied from FLAC to MP3 via mutagen.

    Args:
        source:    Absolute path to the source FLAC file.
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

    try:
        flac_tags: Optional[FLAC] = FLAC(source)
    except Exception as e:
        flac_tags = None
        logger.warning("Could not read FLAC tags from %s: %s", source, e)

    dest_dir.mkdir(parents=True, exist_ok=True)
    mp3_name = _build_mp3_filename(source, flac_tags)
    dest_path = dest_dir / mp3_name

    if dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", dest_path)
        return dest_path

    _run_ffmpeg_transcode(source, dest_path, bitrate=bitrate, ffmpeg_path=None)
    _apply_id3_tags(dest_path, flac_tags, prune_existing=True)

    logger.info("Transcoded: %s -> %s", source, dest_path)
    return dest_path


def build_dj_copy_filename(source_flac: Path) -> str:
    """Return the DJ-copy filename for a FLAC source (no I/O besides tag read)."""
    try:
        flac_tags: Optional[FLAC] = FLAC(source_flac)
    except Exception as e:
        flac_tags = None
        logger.warning("Could not read FLAC tags from %s: %s", source_flac, e)
    return _build_mp3_filename(source_flac, flac_tags)


def tag_mp3_as_dj_copy(mp3_path: Path, source_flac: Path) -> None:
    """Apply the DJ tag policy to an existing MP3, pruning to the DJ-managed frames."""
    flac_tags: Optional[FLAC] = FLAC(source_flac)
    _apply_id3_tags(mp3_path, flac_tags, prune_existing=True)


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

    try:
        flac_tags: Optional[FLAC] = FLAC(source)
    except Exception as e:
        flac_tags = None
        logger.warning("Could not read FLAC tags from %s: %s", source, e)

    resolved_snapshot = _snapshot_with_flac_fallback(snapshot, flac_tags)
    if not resolved_snapshot.artist or not resolved_snapshot.title:
        raise TranscodeError(f"DJ snapshot export requires artist/title metadata: {source}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final_dest_path = dest_path or (dest_dir / _build_snapshot_mp3_filename(source, resolved_snapshot))

    final_dest_path.parent.mkdir(parents=True, exist_ok=True)

    if final_dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", final_dest_path)
        return final_dest_path

    _run_ffmpeg_transcode(source, final_dest_path, bitrate=bitrate, ffmpeg_path=ffmpeg_path)
    _apply_snapshot_id3_tags(final_dest_path, resolved_snapshot, flac_tags, prune_existing=True)

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
    """Transcode a FLAC to MP3 and apply a broader, library-friendly tag set."""
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    _check_ffmpeg(ffmpeg_path)

    try:
        flac_tags: Optional[FLAC] = FLAC(source)
    except Exception as e:
        flac_tags = None
        logger.warning("Could not read FLAC tags from %s: %s", source, e)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and not overwrite:
        logger.info("Skipping transcode, already exists: %s", dest_path)
        return dest_path

    _run_ffmpeg_transcode(source, dest_path, bitrate=bitrate, ffmpeg_path=ffmpeg_path)
    _apply_full_id3_tags(dest_path, flac_tags)
    logger.info("Transcoded (full tags): %s -> %s", source, dest_path)
    return dest_path


def _run_ffmpeg_transcode(
    source: Path,
    dest_path: Path,
    *,
    bitrate: int,
    ffmpeg_path: str | None,
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


def sync_dj_mp3_from_flac(mp3_path: Path, source_flac: Path) -> None:
    """Refresh DJ MP3 tags/artwork from an enriched source FLAC."""
    flac_tags = FLAC(source_flac)
    _apply_id3_tags(mp3_path, flac_tags, prune_existing=False)


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
    flac_tags: Optional[FLAC],
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
    if flac_tags is None:
        tags.save(mp3_path)
        return

    def first(key: str) -> Optional[str]:
        vals = flac_tags.get(key)
        return vals[0] if vals else None

    _apply_dj_tag_policy(tags, flac_tags, first)
    tags.save(mp3_path)


def _apply_full_id3_tags(mp3_path: Path, flac_tags: Optional[FLAC]) -> None:
    tags = _empty_id3()
    if flac_tags is None:
        tags.save(mp3_path)
        return

    def first(key: str) -> Optional[str]:
        vals = flac_tags.get(key)
        return vals[0] if vals else None

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

    _apply_cover_art(tags, flac_tags)
    tags.save(mp3_path)


def _apply_snapshot_id3_tags(
    mp3_path: Path,
    snapshot: DjTagSnapshot,
    flac_tags: Optional[FLAC],
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
    if flac_tags is not None:
        _apply_cover_art(tags, flac_tags)
    tags.save(mp3_path)


def _clear_dj_managed_frames(tags: ID3) -> None:
    for frame_id in DJ_MANAGED_FRAMES:
        _id3_delall(tags, frame_id)


def _apply_dj_tag_policy(tags: ID3, flac_tags: FLAC, first: TagLookup) -> None:
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

    _apply_cover_art(tags, flac_tags)


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


def _apply_cover_art(tags: ID3, flac_tags: FLAC) -> None:
    pictures = getattr(flac_tags, "pictures", None) or []
    if not pictures:
        return

    front_cover = None
    for picture in pictures:
        if getattr(picture, "type", None) == 3:
            front_cover = picture
            break
    if front_cover is None:
        front_cover = pictures[0]

    data = getattr(front_cover, "data", None)
    if not data:
        return

    _id3_delall(tags, "APIC")
    _id3_add(tags, _apic_frame(data, getattr(front_cover, "mime", "image/jpeg") or "image/jpeg"))
