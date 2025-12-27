"""Typed data models for persisted audio files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Any


@dataclass(slots=True)
class AudioFile:
    """Typed record representing a tracked audio file."""

    path: Path
    checksum: str | None
    duration: float | None
    bit_depth: int | None
    sample_rate: int | None
    bitrate: int | None
    metadata: Mapping[str, Any]
    flac_ok: bool | None
    library_state: Literal["STAGING", "FINAL", "ARCHIVED"]
    acoustid: str | None = None
