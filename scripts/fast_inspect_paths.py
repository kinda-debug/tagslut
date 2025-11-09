"""Fast inspect paths using ffprobe-only metadata (reported/decoded durations).

This script is intended to be quick and safe: it does not run expensive
PCM SHA1 or Chromaprint fingerprinting. Use it when you want a fast view of
reported vs decoded durations for a list of paths.

Usage:
    python3 scripts/fast_inspect_paths.py --paths /tmp/top50_paths.txt --output /tmp/quarantine_fast_analysis_top50.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List, Optional

from dedupe import quarantine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--paths", required=True, help="File with one absolute path per line")
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
            text = line.strip().strip('"')
            if text:
                paths.append(Path(text))

    rows = []
    for path in paths:
        try:
            reported, decoded = quarantine.detect_length_mismatch(path)
            size = path.stat().st_size if path.exists() else 0
            ratio: Optional[float]
            try:
                ratio = (decoded / reported) if (reported and decoded) else None
            except Exception:
                ratio = None
            rows.append({
                "path": str(path),
                "size": size,
                "reported": reported,
                "decoded": decoded,
                "ratio": ratio,
            })
        except Exception as exc:
            rows.append({
                "path": str(path),
                "size": 0,
                "reported": None,
                "decoded": None,
                "ratio": None,
                "error": str(exc),
            })

    fieldnames = ["path", "size", "reported", "decoded", "ratio"]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            # only write the expected fields to keep CSV stable
            writer.writerow({k: r.get(k) for k in fieldnames})

    print(f"Wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
