"""Playlist export utilities.

This module converts match results into various output formats.  It depends
on :mod:`audio_suite.plugins.match.engine` to obtain the matching data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...core import config as core_config
from ...core import db as core_db
from ...plugins.match import engine as match_engine


def export(
    playlist_path: str,
    fmt: str,
    settings: Any,
    output: Optional[Path] = None,
) -> Path:
    """Export match results to the given format and return the output path.

    Supported formats:

    - ``m3u`` – a simple list of matched file paths
    - ``json`` – a JSON array of objects containing the query, match and score
    - ``songshift`` – a SongShift compatible JSON containing unmatched entries
    """
    fmt = fmt.lower()
    engine = core_db.get_engine(settings)
    core_db.initialise_database(engine)
    results = match_engine.match_playlist(playlist_path, engine, settings, review=False)

    # Determine destination path
    playlist_name = Path(playlist_path).stem
    if output is None:
        if fmt == "m3u":
            template = settings.get("match_output_path_m3u")
        elif fmt == "json":
            template = settings.get("match_output_path_json")
        elif fmt == "songshift":
            template = f"{playlist_name}_songshift.json"
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
        output = Path(template.format(playlist_name=playlist_name)).expanduser().resolve()
    else:
        output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "m3u":
        lines = [r["match"] for r in results if r["match"]]
        output.write_text("\n".join(lines), encoding="utf-8")
    elif fmt == "json":
        output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    elif fmt == "songshift":
        unmatched = [r["query"] for r in results if not r["match"]]
        output.write_text(json.dumps({"tracks": unmatched}, indent=2), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
    return output