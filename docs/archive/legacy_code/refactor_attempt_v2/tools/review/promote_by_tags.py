#!/usr/bin/env python3
"""
Promote FLAC files into a canonical layout using tags.

IMPORTANT: This script is a core part of the workflow and should NOT be removed.

Features:
- Organizes files based on tags (artist, album, year, etc.)
- Preserves ALL metadata including MusicBrainz IDs
- Tracks promotions in database for audit trail
- Maintains AcoustID and duration data for integrity validation

Duration & AcoustID Integration:
- Duration alone is insufficient for identifying issues
- MusicBrainz track length is compared with actual duration to detect:
  * Stitched files (R-Studio recoveries that are too long)
  * Truncated files (incomplete or corrupt, too short)
- AcoustID fingerprints verify audio content matches expected recording
- Combined approach catches both metadata AND audio corruption

See docs/DURATION_VALIDATION.md for details on duration-based integrity checks.

Dry-run by default; use --execute to copy/move files.
Naming rules match the Picard template:
  - Top folder: label (if compilation) else albumartist/artist
  - Album folder: (YYYY) Album + optional [Bootleg]/[Live]/[Compilation]/[Soundtrack]/[EP]/[Single]
  - Filename: NN. <Artist - >Title with featuring -> feat.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Iterable, TextIO

from mutagen import MutagenError  # type: ignore[attr-defined]
from mutagen.flac import FLAC, FLACNoHeaderError

from dedupe.utils.db import open_db

TRUTHY = {"1", "true", "yes", "y", "t"}


def normalize_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        if isinstance(item, bytes):
            out.append(item.decode("utf-8", errors="ignore"))
        else:
            out.append(str(item))
    return [v for v in out if v]


def load_tags(path: Path) -> dict[str, list[str]]:
    audio = FLAC(path)
    tags: dict[str, list[str]] = {}
    if audio.tags and hasattr(audio.tags, "items"):
        for key, value in audio.tags.items():
            tags[key.lower()] = normalize_values(value)
    return tags


def first_tag(tags: dict[str, list[str]], keys: Iterable[str]) -> str:
    for key in keys:
        vals = tags.get(key)
        if vals:
            return vals[0]
    return ""
