"""
FLAC to MP3 transcoder for DJ pool export.

Master FLAC files are NEVER modified. MP3 is written to dest_dir.
All tags are copied from source FLAC to output MP3 via mutagen.
Requires ffmpeg installed as a system dependency.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from mutagen.flac import FLAC
from mutagen.id3 import ID3, TALB, TBPM, TCON, TDRC, TIT2, TKEY, TPE1, TSRC  # type: ignore  # TODO: mypy-strict

logger = logging.getLogger(__name__)


class TranscodeError(Exception):
    pass


class FFmpegNotFoundError(TranscodeError):
    pass


def _check_ffmpeg() -> None:
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

    cmd = [
        "ffmpeg",
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
        "0",
        str(dest_path),
    ]
    logger.debug("Transcoding: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise TranscodeError(
            f"ffmpeg failed for {source}:\n{result.stderr[-500:]}"
        )

    _apply_id3_tags(dest_path, flac_tags)

    logger.info("Transcoded: %s -> %s", source, dest_path)
    return dest_path


def _apply_id3_tags(mp3_path: Path, flac_tags: Optional[FLAC]) -> None:
    """Apply critical DJ tags to the MP3 via mutagen ID3."""
    if flac_tags is None:
        return
    try:
        tags = ID3(mp3_path)  # type: ignore  # TODO: mypy-strict
    except Exception as e:
        logger.warning("Could not load existing ID3 tags from %s: %s", mp3_path, e)
        tags = ID3()  # type: ignore  # TODO: mypy-strict

    def first(key: str) -> Optional[str]:
        vals = flac_tags.get(key)
        return vals[0] if vals else None

    if first("title"):
        tags["TIT2"] = TIT2(encoding=3, text=first("title"))  # type: ignore  # TODO: mypy-strict
    if first("artist") or first("albumartist"):
        tags["TPE1"] = TPE1(  # type: ignore  # TODO: mypy-strict
            encoding=3,
            text=first("artist") or first("albumartist"),
        )
    if first("album"):
        tags["TALB"] = TALB(encoding=3, text=first("album"))  # type: ignore  # TODO: mypy-strict
    if first("date") or first("year"):
        tags["TDRC"] = TDRC(encoding=3, text=first("date") or first("year"))  # type: ignore  # TODO: mypy-strict
    if first("genre"):
        tags["TCON"] = TCON(encoding=3, text=first("genre"))  # type: ignore  # TODO: mypy-strict
    if first("bpm"):
        tags["TBPM"] = TBPM(encoding=3, text=first("bpm"))  # type: ignore  # TODO: mypy-strict
    if first("initialkey") or first("key"):
        tags["TKEY"] = TKEY(encoding=3, text=first("initialkey") or first("key"))  # type: ignore  # TODO: mypy-strict
    if first("isrc"):
        tags["TSRC"] = TSRC(encoding=3, text=first("isrc"))  # type: ignore  # TODO: mypy-strict

    tags.save(mp3_path)
