"""Health scoring for FLAC files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

from mutagen._util import MutagenError
from mutagen.flac import FLAC


def _clamp_score(value: float) -> float:
    """Return *value* limited to the inclusive range [0.0, 10.0]."""
    return max(0.0, min(10.0, round(value, 1)))


def _has_replaygain(tags: dict[str, list[str]]) -> bool:
    """Return ``True`` if any ReplayGain-related tag is present."""
    rg_keys = {"replaygain_track_gain", "replaygain_album_gain", "rg_audiophile"}
    lower_keys = {str(key).lower() for key in tags.keys()}
    return any(key in lower_keys for key in rg_keys)


def _candidate_values(tags: dict[str, list[str]]) -> Iterable[str]:
    """Yield tag values used for plausibility checks."""
    for key in ("genre", "style", "mood"):
        for value in tags.get(key, []):
            yield value


def _is_long_form(tags: dict[str, list[str]]) -> bool:
    """Return ``True`` when tags suggest classical or ambient content."""
    return any(
        "classical" in value.lower() or "ambient" in value.lower()
        for value in _candidate_values(tags)
    )


def score_flac(path: str) -> Dict[str, Any]:
    """Compute a 0–10 health score for the FLAC file at *path*.

    The function performs only read operations. Any mutagen parsing failure
    results in a score of ``0`` with the error recorded in the metrics.
    """
    metrics: Dict[str, Any] = {
        "mutagen_ok": False,
        "mutagen_error": None,
        "header": {},
        "replaygain_present": False,
        "md5_audio_present": False,
        "duration": {},
        "structure": {},
    }
    file_path = Path(path)
    try:
        audio = FLAC(file_path)
        metrics["mutagen_ok"] = True
    except (MutagenError, OSError) as exc:
        metrics["mutagen_error"] = str(exc)
        return {"health_score": 0.0, "metrics": metrics}
    info = audio.info
    # Ensure tags is a dict[str, list[str]]
    tags: dict[str, list[str]] = {}
    if hasattr(audio, "tags") and audio.tags is not None and isinstance(audio.tags, dict):
        for k, v in audio.tags.items():
            if isinstance(v, list):
                tags[str(k)] = [str(vv) for vv in v]
            elif v is not None:
                tags[str(k)] = [str(v)]
    score = 10.0
    header = {
        "sample_rate": getattr(info, "sample_rate", None),
        "bit_depth": getattr(info, "bits_per_sample", None),
        "channels": getattr(info, "channels", None),
        "duration": getattr(info, "length", None),
    }
    metrics["header"] = header
    for field in ("sample_rate", "bit_depth", "channels"):
        if not header.get(field):
            score -= 1.0
    duration_val = header.get("duration")
    if duration_val is None:
        metrics["duration"]["zero_length"] = True
        return {"health_score": 0.0, "metrics": metrics}
    try:
        duration = float(duration_val)
    except (TypeError, ValueError):
        metrics["duration"]["zero_length"] = True
        return {"health_score": 0.0, "metrics": metrics}
    metrics["duration"].update(
        {
            "value": duration,
            "too_short": duration < 5.0,
            "too_long": duration > 1200.0,
        }
    )
    if duration < 5.0:
        score -= 2.0
    if duration > 1200.0 and not _is_long_form(tags):
        score -= 1.0
    metrics["replaygain_present"] = _has_replaygain(tags)
    if metrics["replaygain_present"]:
        score += 0.5
    metrics["md5_audio_present"] = bool(getattr(info, "md5_signature", None))
    if metrics["md5_audio_present"]:
        score += 0.5
    try:
        with file_path.open("rb") as stream:
            prefix = stream.read(4)
            stream.seek(max(file_path.stat().st_size - 2048, 0))
            suffix = stream.read(2048)
    except OSError as exc:
        metrics["structure"] = {"error": str(exc), "prefix_ok": False, "suffix_ok": False}
        score -= 2.0
        return {"health_score": _clamp_score(score), "metrics": metrics}
    prefix_ok = prefix == b"fLaC"
    suffix_ok = len(suffix) > 0
    metrics["structure"] = {"prefix_ok": prefix_ok, "suffix_ok": suffix_ok}
    if not prefix_ok:
        score -= 2.0
    if not suffix_ok:
        score -= 1.0
    return {"health_score": _clamp_score(score), "metrics": metrics}
