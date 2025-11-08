"""Legacy entry point delegating to :mod:`dedupe.quarantine`."""

from __future__ import annotations

import argparse
from pathlib import Path

from dedupe.quarantine import analyse_quarantine, write_analysis_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyse quarantine directory with ffprobe/fpcalc")
    parser.add_argument("--dir", required=True, type=Path, help="Directory to scan")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="CSV output path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files processed",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker threads",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.dir.is_dir():
        parser.error(f"Not a directory: {args.dir}")

    rows = analyse_quarantine(args.dir, limit=args.limit, workers=args.workers)
    if args.out:
        write_analysis_csv(rows, args.out)
        print(f"Wrote {args.out}")
    else:
        for row in rows:
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
