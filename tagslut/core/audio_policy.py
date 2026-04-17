from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping


AudioClassificationKind = Literal[
    "canonical_lossless",
    "provisional_lossy",
    "unsupported",
]

LOSSLESS_CODECS: frozenset[str] = frozenset({
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
})

LOSSY_PROVISIONAL_THRESHOLDS_KBPS: dict[str, int] = {
    "aac": 256,
    "ac3": 256,
    "eac3": 256,
    "mp2": 256,
    "mp3": 320,
    "opus": 256,
    "vorbis": 256,
    "wmav2": 256,
    "wmapro": 256,
}


@dataclass(frozen=True)
class AudioProbe:
    path: Path
    extension: str
    codec_name: str | None
    bitrate_kbps: int | None
    sample_rate: int | None
    bit_depth: int | None


@dataclass(frozen=True)
class AudioClassification:
    kind: AudioClassificationKind
    extension: str
    codec_name: str | None
    bitrate_kbps: int | None
    sample_rate: int | None
    bit_depth: int | None
    threshold_kbps: int | None
    reason: str

    @property
    def accepted(self) -> bool:
        return self.kind != "unsupported"


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


def _bitrate_kbps(value: Any) -> int | None:
    bitrate_bps = _safe_int(value)
    if bitrate_bps is None:
        return None
    if bitrate_bps <= 0:
        return None
    return bitrate_bps // 1000


def _infer_bit_depth(stream: Mapping[str, Any]) -> int | None:
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        value = _safe_int(stream.get(key))
        if value:
            return value
    sample_fmt = str(stream.get("sample_fmt") or "").strip().lower()
    digits = "".join(ch for ch in sample_fmt if ch.isdigit())
    if digits:
        return _safe_int(digits)
    return None


def probe_from_stream(path: Path, stream: Mapping[str, Any]) -> AudioProbe:
    codec_name = str(stream.get("codec_name") or "").strip().lower() or None
    sample_rate = _safe_int(stream.get("sample_rate"))
    bit_depth = _infer_bit_depth(stream)
    return AudioProbe(
        path=path,
        extension=path.suffix.lower(),
        codec_name=codec_name,
        bitrate_kbps=_bitrate_kbps(stream.get("bit_rate")),
        sample_rate=sample_rate,
        bit_depth=bit_depth,
    )


def probe_from_technical(
    path: Path,
    *,
    codec_name: str | None,
    bitrate_bps: int | None,
    sample_rate: int | None,
    bit_depth: int | None,
) -> AudioProbe:
    return AudioProbe(
        path=path,
        extension=path.suffix.lower(),
        codec_name=(codec_name or "").strip().lower() or None,
        bitrate_kbps=_bitrate_kbps(bitrate_bps),
        sample_rate=sample_rate,
        bit_depth=bit_depth,
    )


def classify_audio_probe(probe: AudioProbe) -> AudioClassification:
    codec = (probe.codec_name or "").strip().lower()
    if probe.sample_rate is not None and probe.sample_rate < 44100:
        return AudioClassification(
            kind="unsupported",
            extension=probe.extension,
            codec_name=probe.codec_name,
            bitrate_kbps=probe.bitrate_kbps,
            sample_rate=probe.sample_rate,
            bit_depth=probe.bit_depth,
            threshold_kbps=None,
            reason=f"sample rate below 44.1kHz: {probe.sample_rate}",
        )
    if probe.bit_depth is not None and probe.bit_depth < 16:
        return AudioClassification(
            kind="unsupported",
            extension=probe.extension,
            codec_name=probe.codec_name,
            bitrate_kbps=probe.bitrate_kbps,
            sample_rate=probe.sample_rate,
            bit_depth=probe.bit_depth,
            threshold_kbps=None,
            reason=f"bit depth below 16-bit: {probe.bit_depth}",
        )

    if codec in LOSSLESS_CODECS:
        return AudioClassification(
            kind="canonical_lossless",
            extension=probe.extension,
            codec_name=probe.codec_name,
            bitrate_kbps=probe.bitrate_kbps,
            sample_rate=probe.sample_rate,
            bit_depth=probe.bit_depth,
            threshold_kbps=None,
            reason=f"lossless codec accepted: {probe.codec_name}",
        )

    threshold = LOSSY_PROVISIONAL_THRESHOLDS_KBPS.get(codec)
    if threshold is not None:
        if probe.bitrate_kbps is None:
            return AudioClassification(
                kind="unsupported",
                extension=probe.extension,
                codec_name=probe.codec_name,
                bitrate_kbps=None,
                sample_rate=probe.sample_rate,
                bit_depth=probe.bit_depth,
                threshold_kbps=threshold,
                reason=f"missing bitrate evidence for lossy codec: {probe.codec_name}",
            )
        if probe.bitrate_kbps >= threshold:
            return AudioClassification(
                kind="provisional_lossy",
                extension=probe.extension,
                codec_name=probe.codec_name,
                bitrate_kbps=probe.bitrate_kbps,
                sample_rate=probe.sample_rate,
                bit_depth=probe.bit_depth,
                threshold_kbps=threshold,
                reason=(
                    f"lossy codec accepted provisionally: {probe.codec_name} "
                    f"{probe.bitrate_kbps}kbps >= {threshold}kbps"
                ),
            )
        return AudioClassification(
            kind="unsupported",
            extension=probe.extension,
            codec_name=probe.codec_name,
            bitrate_kbps=probe.bitrate_kbps,
            sample_rate=probe.sample_rate,
            bit_depth=probe.bit_depth,
            threshold_kbps=threshold,
            reason=(
                f"lossy codec below provisional threshold: {probe.codec_name} "
                f"{probe.bitrate_kbps}kbps < {threshold}kbps"
            ),
        )

    return AudioClassification(
        kind="unsupported",
        extension=probe.extension,
        codec_name=probe.codec_name,
        bitrate_kbps=probe.bitrate_kbps,
        sample_rate=probe.sample_rate,
        bit_depth=probe.bit_depth,
        threshold_kbps=None,
        reason=f"unsupported codec: {probe.codec_name or 'unknown'}",
    )
