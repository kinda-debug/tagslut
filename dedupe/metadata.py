"""Metadata extraction helpers for audio files."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AudioStreamInfo:
    """Basic technical information about an audio stream."""

    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]


@dataclass(slots=True)
class FileMetadata:
    """Complete metadata bundle returned by :func:`probe_audio`."""

    path: Path
    size_bytes: int
    stream: AudioStreamInfo
    tags: Dict[str, Any]


def _run_ffprobe(path: Path, timeout: int = 8) -> Optional[dict]:
    ffprobe = which("ffprobe")
    if ffprobe is None:
        LOGGER.debug(
            "ffprobe not available in PATH; skipping probe for %s",
            path,
        )
        return None

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:format_tags",
        "-show_entries",
        (
            "stream=index,codec_type,channels,"
            "sample_rate,bit_rate,bits_per_raw_sample"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.warning("ffprobe invocation failed for %s: %s", path, exc)
        return None

    if result.returncode != 0:
        LOGGER.warning(
            "ffprobe returned non-zero exit status %s for %s",
            result.returncode,
            path,
        )
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        LOGGER.error("Unable to parse ffprobe output for %s: %s", path, exc)
        return None


def _parse_stream_info(payload: dict) -> AudioStreamInfo:
    streams = payload.get("streams") or []
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        {},
    )
    duration = payload.get("format", {}).get("duration")
    tags = payload.get("format", {}).get("tags") or {}

    def _maybe_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    info = AudioStreamInfo(
        duration=float(duration) if duration is not None else None,
        sample_rate=_maybe_int(audio_stream.get("sample_rate")),
        bit_rate=_maybe_int(
            audio_stream.get("bit_rate")
            or payload.get("format", {}).get("bit_rate")
        ),
        channels=_maybe_int(audio_stream.get("channels")),
        bit_depth=_maybe_int(audio_stream.get("bits_per_raw_sample")),
    )

    if info.bit_depth is None:
        # Some formats store depth in tag form (e.g. WAV "bits_per_sample")
        info.bit_depth = _maybe_int(tags.get("bits_per_sample"))

    return info


def _extract_tags(path: Path) -> Dict[str, Any]:
    try:
        import mutagen  # type: ignore
    except ImportError:
        return {}

    try:
        audio = mutagen.File(path)
    except Exception as exc:  # pragma: no cover - mutagen failures
        LOGGER.debug("mutagen failed to parse %s: %s", path, exc)
        return {}

    if audio is None or not hasattr(audio, "tags") or audio.tags is None:
        return {}

    tags: Dict[str, Any] = {}
    for key, value in audio.tags.items():
        if isinstance(value, (list, tuple)):
            tags[key] = [str(item) for item in value]
        else:
            tags[key] = str(value)
    return tags


def probe_audio(path: Path) -> FileMetadata:
    """Return :class:`FileMetadata` for *path* using ffprobe and mutagen."""

    stat = path.stat()
    payload = _run_ffprobe(path)
    stream = _parse_stream_info(payload or {})
    tags = _extract_tags(path) if payload is not None else {}
    return FileMetadata(
        path=path,
        size_bytes=stat.st_size,
        stream=stream,
        tags=tags,
    )
