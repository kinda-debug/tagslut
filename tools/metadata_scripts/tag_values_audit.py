#!/usr/bin/env python3
"""Extract key tag values after tagging.

Outputs a CSV with bpm/key/genre/style/isrc/energy/danceability and other common tags.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from mutagen import File as MutagenFile

AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
}


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _read_m3u_lines(m3u_path: Path) -> list[Path]:
    paths: list[Path] = []
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        paths.append(Path(value).expanduser())
    return paths


def _collect_audio_paths(path: Path) -> list[Path]:
    if not path.exists():
        raise SystemExit(f"Path not found: {path}")
    if path.is_file():
        if path.suffix.lower() in {".m3u", ".m3u8"}:
            return _read_m3u_lines(path)
        return [path]
    results: list[Path] = []
    for item in path.rglob("*"):
        if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS:
            results.append(item)
    return results


def _get_easy(audio_path: Path) -> dict[str, list[str]]:
    try:
        audio = MutagenFile(str(audio_path), easy=True)
    except Exception:
        return {}
    if audio is None or not audio.tags:
        return {}
    return {str(k).lower(): [str(v) for v in vals] for k, vals in audio.tags.items()}


def _first(tags: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        vals = tags.get(key.lower())
        if vals:
            return str(vals[0])
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract tag values for audit.")
    parser.add_argument("--path", required=True, help="Path to files or M3U.")
    parser.add_argument("--output", default="", help="CSV output path.")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    items = _collect_audio_paths(path)

    out_path = Path(args.output) if args.output else Path.cwd() / f"tag_values_{_now_stamp()}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "path",
        "genre",
        "style",
        "bpm",
        "key",
        "isrc",
        "label",
        "remixer",
        "version",
        "energy",
        "danceability",
        "comment",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in items:
            tags = _get_easy(item)
            writer.writerow(
                {
                    "path": str(item),
                    "genre": _first(tags, "genre", "genres"),
                    "style": _first(tags, "style"),
                    "bpm": _first(tags, "bpm"),
                    "key": _first(tags, "key"),
                    "isrc": _first(tags, "isrc"),
                    "label": _first(tags, "label"),
                    "remixer": _first(tags, "remixer"),
                    "version": _first(tags, "version", "mixname"),
                    "energy": _first(tags, "1t_energy", "energy"),
                    "danceability": _first(tags, "1t_danceability", "danceability"),
                    "comment": _first(tags, "comment"),
                }
            )

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
