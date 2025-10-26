#!/usr/bin/env python3
"""Utility for converting `_BROKEN_FILES.txt` into a playable M3U list."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path("/Volumes/dotad/MUSIC")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Return parsed CLI arguments for playlist generation."""

    parser = argparse.ArgumentParser(
        description="Convert the broken files log into an M3U playlist",
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="Music library root (default: /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--input",
        "-i",
        dest="input_path",
        help="Path to the broken files log (defaults to <root>/_BROKEN_FILES.txt)",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_path",
        help="Destination playlist path (defaults to <root>/broken_files_unrepaired.m3u)",
    )
    return parser.parse_args(argv)


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    """Resolve input/output paths based on CLI arguments."""

    root = Path(args.root).expanduser()
    input_path = Path(args.input_path).expanduser() if args.input_path else root / "_BROKEN_FILES.txt"
    output_path = Path(args.output_path).expanduser() if args.output_path else root / "broken_files_unrepaired.m3u"
    return input_path, output_path


def build_playlist(input_path: Path, output_path: Path) -> int:
    """Read *input_path* and write a playlist to *output_path*."""

    if not input_path.exists():
        print(f"Input log not found: {input_path}")
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with input_path.open("r", encoding="utf-8") as fin, output_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            candidate = parts[1] if len(parts) >= 2 else parts[0]
            fout.write(f"{candidate}\n")
            written += 1

    print(f"Playlist written to {output_path} ({written} entries)")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    input_path, output_path = resolve_paths(args)
    return build_playlist(input_path, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
