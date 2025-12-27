"""Read-only FLAC health scoring utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from . import metadata

try:  # pragma: no cover - optional dependency
    from mutagen import MutagenError
    from mutagen.flac import FLAC
except ImportError:  # pragma: no cover - optional dependency
    FLAC = None  # type: ignore
    MutagenError = Exception


def score_file(path: str) -> Tuple[int, Dict[str, Any]]:
    """Return a 0–10 health score and metadata summary for ``path``.

    The function is read-only and defensive: any exception results in a score of
    ``0``. The accompanying info dictionary reports validation outcomes and
    discovered metadata fields.
    """

    info: Dict[str, Any] = {
        "exists": False,
        "readable": False,
        "is_flac": False,
        "size": None,
        "duration": None,
        "sample_rate": None,
        "channels": None,
        "bit_depth": None,
        "tags_ok": None,
        "md5_ok": None,
    }

    try:
        path_obj = Path(path)
    except Exception:
        return 0, info

    info["exists"] = path_obj.is_file()
    if not info["exists"]:
        return 0, info

    info["is_flac"] = path_obj.suffix.lower() == ".flac"

    try:
        with open(path_obj, "rb"):
            info["readable"] = True
    except OSError:
        return 0, info

    if not info["is_flac"]:
        return 0, info

    try:
        meta = metadata.probe_audio(path_obj)
    except Exception:
        return 0, info

    info.update(
        {
            "size": meta.size_bytes,
            "duration": meta.stream.duration,
            "sample_rate": meta.stream.sample_rate,
            "channels": meta.stream.channels,
            "bit_depth": meta.stream.bit_depth,
        }
    )

    try:
        json.dumps(meta.tags, sort_keys=True)
    except (TypeError, ValueError):
        info["tags_ok"] = False
    else:
        info["tags_ok"] = True

    md5_ok = None
    if FLAC is not None:
        try:
            audio = FLAC(path_obj)
            md5_ok = bool(getattr(audio.info, "md5_signature", None))
        except (MutagenError, OSError, AttributeError):
            md5_ok = False
    info["md5_ok"] = md5_ok

    score = 0
    audio_stream_ok = meta.stream.duration is not None or meta.stream.sample_rate is not None
    if audio_stream_ok:
        score += 2
    if md5_ok:
        score += 2
    if info["tags_ok"]:
        score += 2
    if info["duration"] is not None and info["duration"] > 0:
        score += 2
    if (
        info["sample_rate"] is not None
        and info["sample_rate"] > 0
        and info["channels"] is not None
        and info["channels"] > 0
    ):
        score += 2

    return min(score, 10), info
