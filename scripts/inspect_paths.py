"""Inspect specific FLAC paths using the package analyse functions.

Usage:
    python3 scripts/inspect_paths.py \
        --paths /tmp/top50_paths.txt \
        --output /tmp/quarantine_analysis_top50.csv

The script imports `dedupe.quarantine.analyse_track` so it runs the same
analysis used by the CLI (ffprobe, PCM SHA1, fingerprint count).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from dedupe import quarantine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--paths",
        required=True,
        help="File containing one absolute path per line",
    )
    p.add_argument("--output", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    p = Path(args.paths)
    if not p.exists():
        raise SystemExit(f"Paths file not found: {p}")
    paths: List[Path] = []
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                paths.append(Path(line))

    rows = []
    for path in paths:
        try:
            rows.append(quarantine.analyse_track(path))
        except Exception as exc:
            rows.append({
                "path": str(path),
                "size": 0,
                "reported_duration": None,
                "decoded_duration": None,
                "sample_rate": None,
                "channels": None,
                "pcm_sha1": None,
                "window_fingerprint_count": 0,
                "stitched_flag": False,
                "truncated_flag": False,
                "error": str(exc),
            })

    quarantine.write_analysis_csv(rows, Path(args.output))
    print(f"Wrote {args.output} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
