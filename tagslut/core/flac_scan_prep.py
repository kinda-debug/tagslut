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

from tagslut.core.audio_policy import classify_audio_probe, probe_from_stream
from tagslut.utils import AUDIO_EXTENSIONS


@dataclass(frozen=True)
class PreparedFlacInput:
    source_path: Path
    scan_path: Path | None
    original_path: Path
    converted: bool
    codec_name: str | None = None
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    bit_depth: int | None = None
    classification: str | None = None
    classification_reason: str | None = None
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
            classification="canonical_lossless",
        )

    if suffix not in AUDIO_EXTENSIONS:
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
            classification="canonical_lossless",
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

    probe = probe_from_stream(source_path, stream)
    classification = classify_audio_probe(probe)

    if not classification.accepted:
        skip_reason = "unsupported_codec"
        if classification.reason.startswith("sample rate below 44.1kHz"):
            skip_reason = "sample_rate_too_low"
        elif classification.reason.startswith("bit depth below 16-bit"):
            skip_reason = "bit_depth_too_low"
        elif classification.reason.startswith("lossy codec below provisional threshold"):
            skip_reason = "lossy_below_threshold"
        elif classification.reason.startswith("missing bitrate evidence"):
            skip_reason = "lossy_bitrate_missing"

        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=classification.codec_name,
            bitrate_kbps=classification.bitrate_kbps,
            sample_rate=classification.sample_rate,
            bit_depth=classification.bit_depth,
            classification=classification.kind,
            classification_reason=classification.reason,
            skip_reason=skip_reason,
            message=classification.reason,
        )

    if shutil.which("ffmpeg") is None:
        return PreparedFlacInput(
            source_path=source_path,
            scan_path=None,
            original_path=source_path,
            converted=False,
            codec_name=classification.codec_name,
            bitrate_kbps=classification.bitrate_kbps,
            sample_rate=classification.sample_rate,
            bit_depth=classification.bit_depth,
            classification=classification.kind,
            classification_reason=classification.reason,
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
            codec_name=classification.codec_name,
            bitrate_kbps=classification.bitrate_kbps,
            sample_rate=classification.sample_rate,
            bit_depth=classification.bit_depth,
            classification=classification.kind,
            classification_reason=classification.reason,
            skip_reason="conversion_failed",
            message=error or "ffmpeg conversion failed",
        )

    return PreparedFlacInput(
        source_path=source_path,
        scan_path=scan_path,
        original_path=source_path,
        converted=True,
        codec_name=classification.codec_name,
        bitrate_kbps=classification.bitrate_kbps,
        sample_rate=classification.sample_rate,
        bit_depth=classification.bit_depth,
        classification=classification.kind,
        classification_reason=classification.reason,
        message=f"converted {suffix or '<none>'} -> .flac ({classification.kind})",
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
        "stream=codec_name,sample_rate,bit_rate,bits_per_sample,bits_per_raw_sample,sample_fmt",
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
