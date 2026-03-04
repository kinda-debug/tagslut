#!/usr/bin/env python3
"""
Standalone canonizer for FLAC tags using tools/rules/library_canon.json.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mutagen.flac import FLAC

from tagslut.metadata.canon import load_canon_rules, apply_canon, canon_diff
from tagslut.utils.paths import list_files
from _progress import ProgressTracker


def collect_flacs(path: Path) -> list[Path]:
    if path.is_dir():
        return list(list_files(path, {".flac"}))
    if path.is_file():
        return [path]
    raise SystemExit(f"Path not found: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonize FLAC tags using library_canon.json")
    parser.add_argument("path", type=Path, help="File or directory to process")
    parser.add_argument("--canon-rules", type=Path, help="Path to canon rules JSON")
    parser.add_argument("--canon-dry-run", action="store_true", help="Print before/after diff for one file and exit")
    parser.add_argument("--execute", action="store_true", help="Write tags (default: dry-run)")
    parser.add_argument("--limit", type=int, help="Maximum files to process")
    parser.add_argument("--progress-interval", type=int, default=50, help="Progress print interval")
    args = parser.parse_args()

    rules_path = args.canon_rules or (Path(__file__).parents[2] / "tools" / "rules" / "library_canon.json")
    rules = load_canon_rules(rules_path)

    files = collect_flacs(args.path.expanduser().resolve())
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("No FLAC files found.")
        return 0

    if args.canon_dry_run:
        audio = FLAC(files[0])
        before = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
        after = apply_canon(before, rules)
        diff = canon_diff(before, after)
        print(diff or "(no changes)")
        return 0

    if not args.execute:
        print("DRY-RUN: use --execute to write tags")

    progress = ProgressTracker(total=len(files), interval=int(args.progress_interval), label="Canonize")
    for idx, path in enumerate(files, start=1):
        audio = FLAC(path)
        before = {k: list(v) if isinstance(v, list) else v for k, v in audio.tags.items()}
        after = apply_canon(before, rules)
        if args.execute:
            audio.clear()
            for key, value in after.items():
                if isinstance(value, (list, tuple)):
                    audio[key] = [str(v) for v in value]
                else:
                    audio[key] = str(value)
            audio.save()
        if progress.should_print(idx):
            print(progress.line(idx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
