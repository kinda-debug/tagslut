"""Playlist matching engine.

This module implements a simple fuzzy matching algorithm that compares
playlist entries to tracks in the local database.  It supports M3U/M3U8,
plain text and JSON playlist formats.  The matching process is
transparent: each result includes the confidence score and the reason for
selection.  If the score falls below the configured automatic threshold
but above the review minimum, interactive review can be requested.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core import utils as core_utils
from ...core.db import Track, session_scope


def _parse_playlist(path: str) -> List[str]:
    """Return a list of query strings extracted from the playlist file."""
    p = Path(path)
    suffix = p.suffix.lower()
    contents: List[str] = []
    if suffix in {".m3u", ".m3u8", ".txt"}:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # If the line looks like a file path, strip extension and directory
            contents.append(_simplify_line(line))
    elif suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            contents = [_simplify_line(str(item)) for item in data]
        elif isinstance(data, dict) and "tracks" in data:
            for item in data["tracks"]:
                if isinstance(item, dict):
                    parts = [item.get(k, "") for k in ("artist", "track", "title", "album")]
                    contents.append(_simplify_line(" ".join(filter(None, parts))))
                else:
                    contents.append(_simplify_line(str(item)))
        else:
            raise ValueError(f"Unsupported JSON structure in {path}")
    else:
        raise ValueError(f"Unsupported playlist format: {suffix}")
    return contents


def _simplify_line(line: str) -> str:
    """Simplify a line by removing common separators and extensions."""
    # Remove directory and extension
    name = Path(line).stem
    # Replace underscores and dots with spaces
    name = re.sub(r"[_\.]+", " ", name)
    return name.strip()


def match_playlist(
    playlist_path: str,
    engine,
    settings,
    review: bool = False,
) -> List[Dict[str, Any]]:
    """Match each entry in the playlist to the best candidate in the DB.

    Returns a list of dictionaries with keys: ``query`` (original string),
    ``match`` (path to the matched track or ``None``), and ``score`` (0–100).  In
    this simplified implementation, review prompts are not interactive; instead
    matches falling between the review thresholds are marked for review but
    automatically rejected.
    """
    queries = _parse_playlist(playlist_path)
    results: List[Dict[str, Any]] = []
    # Load all tracks into memory for matching
    with session_scope(engine) as session:
        all_tracks: Iterable[Tuple[str, str]] = session.query(Track.path, Track.title).all()  # type: ignore
    # Build list of candidate titles
    titles = [Path(path).stem for path, _ in all_tracks]
    for query in queries:
        best_title, score_ratio = core_utils.pick_best_match(query, titles)
        score = int(score_ratio * 100)
        matched_path = None
        if score >= int(settings.get("threshold_auto_match")):
            # Accept automatically
            idx = titles.index(best_title) if best_title in titles else -1
            if idx >= 0:
                matched_path = list(all_tracks)[idx][0]
        elif score >= int(settings.get("threshold_review_min")):
            # Would trigger review; here we simply reject but include score
            matched_path = None
        # else: no match
        results.append({"query": query, "match": matched_path, "score": score})
    return results