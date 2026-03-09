from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


LOSSY_EXTENSIONS = {".mp3", ".aac", ".ogg", ".opus"}
LOSSLESS_CONTAINER_EXTENSIONS = {".flac", ".wav", ".aif", ".aiff", ".m4a", ".mp4"}
LOSSLESS_CODECS = {
    "flac",
    "alac",
    "wavpack",
    "ape",
    "tta",
    "pcm_s8",
    "pcm_s16be",
    "pcm_s16le",
    "pcm_s24be",
    "pcm_s24le",
    "pcm_s32be",
    "pcm_s32le",
    "pcm_f16be",
    "pcm_f16le",
    "pcm_f24be",
    "pcm_f24le",
    "pcm_f32be",
    "pcm_f32le",
    "pcm_f64be",
    "pcm_f64le",
    "pcm_u8",
}
LOSSY_CODECS = {
    "aac",
    "ac3",
    "eac3",
    "mp2",
    "mp3",
    "opus",
    "vorbis",
    "wmav2",
    "wmapro",
}


@dataclass(frozen=True)
class PreparedFlacInput:
    source_path: Path
    scan_path: Path | None
    original_path: Path
    converted: bool
    codec_name: str | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    skip_reason: str | None = None
    message: str | None = None
    cleanup_path: Path | None = None


def cleanup_prepared_flac_input(prepared: PreparedFlacInput) -> None:
    cleanup_path = prepared.cleanup_path
    if cleanup_path is None:
        return
    try:
        cleanup_path.unlink(missing_ok=True)
    except Exception:
        return


def prepare_flac_scan_input(path: Path, *, persist: bool) -> PreparedFlacInput:
    source_path = path.expanduser().resolve()
    suffix = source_path.suffix.lower()

    if suffix == ".flac":
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=source_path,
            original_path=source_path,
            converted=False,
        )

    if suffix in LOSSY_EXTENSIONS:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            skip_reason="lossy_extension",
            message=f"blocked lossy input: {suffix}",
        )

    if suffix not in LOSSLESS_CONTAINER_EXTENSIONS:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            skip_reason="unsupported_extension",
            message=f"unsupported input extension: {suffix or '<none>'}",
        )

    sibling_flac = source_path.with_suffix(".flac")
    if sibling_flac.exists():
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=sibling_flac,
            original_path=source_path,
            converted=False,
            message="using existing sibling FLAC",
        )

    stream = _probe_audio_stream(source_path)
    if stream is None:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            skip_reason="ffprobe_failed",
            message="could not inspect audio stream with ffprobe",
        )

    codec_name = str(stream.get("codec_name") or "").strip().lower() or None
    sample_rate = _safe_int(stream.get("sample_rate"))
    bit_depth = _infer_bit_depth(stream)

    if codec_name in LOSSY_CODECS:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="lossy_codec",
            message=f"blocked lossy codec: {codec_name}",
        )

    if codec_name not in LOSSLESS_CODECS:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="unsupported_codec",
            message=f"unsupported codec for FLAC conversion: {codec_name or 'unknown'}",
        )

    if sample_rate is not None and sample_rate < 44100:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="sample_rate_too_low",
            message=f"sample rate below 44.1kHz: {sample_rate}",
        )

    if bit_depth is not None and bit_depth < 16:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="bit_depth_too_low",
            message=f"bit depth below 16-bit: {bit_depth}",
        )

    if shutil.which("ffmpeg") is None:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="ffmpeg_missing",
            message="ffmpeg is required to convert non-FLAC inputs",
        )

    cleanup_path: Path | None = None
    if persist:
        scan_path = sibling_flac
    else:
        with tempfile.NamedTemporaryFile(prefix="tagslut_scan_", suffix=".flac", delete=False) as handle:
            scan_path = Path(handle.name)
        cleanup_path = scan_path

    converted, error = _convert_to_flac(source_path, scan_path)
    if not converted:
        if cleanup_path is not None:
            cleanup_prepared_flac_input(
                PreparedFlacInput(
                    source_path=source_path,
                    scan_path=None,
                    original_path=source_path,
                    converted=False,
                    cleanup_path=cleanup_path,
                )
            )
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=codec_name,
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            skip_reason="conversion_failed",
            message=error or "ffmpeg conversion failed",
        )

    return PreparedFlacInput(
        source_path=source_path,
        scan_path=scan_path,
        original_path=source_path,
        converted=True,
        codec_name=codec_name,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        message=f"converted {suffix or '<none>'} -> .flac",
        cleanup_path=cleanup_path,
    )


def _probe_audio_stream(path: Path) -> dict[str, Any] | None:
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,bits_per_sample,bits_per_raw_sample,sample_fmt",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") or []
    if not streams:
        return None
    first = streams[0]
    return first if isinstance(first, dict) else None


def _infer_bit_depth(stream: dict[str, Any]) -> int | None:
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        value = _safe_int(stream.get(key))
        if value:
            return value
    sample_fmt = str(stream.get("sample_fmt") or "").strip().lower()
    match = re.search(r"(\d+)", sample_fmt)
    if match:
        return _safe_int(match.group(1))
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _convert_to_flac(source: Path, dest: Path) -> tuple[bool, str | None]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-map_metadata",
        "0",
        "-c:a",
        "flac",
        "-compression_level",
        "8",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()[:400]

    if shutil.which("flac") is not None:
        verify = subprocess.run(
            ["flac", "-t", "--silent", str(dest)],
            capture_output=True,
            text=True,
            check=False,
        )
        if verify.returncode != 0:
            with contextlib.suppress(Exception):
                os.unlink(dest)
            return False, (verify.stderr or verify.stdout or "").strip()[:400] or "flac verify failed"

    return True, None
