"""Legacy entry point delegating to :mod:`dedupe.quarantine.simple_scan`."""

from __future__ import annotations

import argparse
from pathlib import Path

from dedupe.quarantine import simple_scan, write_rows_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple quarantine metadata scan")
    parser.add_argument("--dir", required=True, type=Path, help="Directory to scan")
    parser.add_argument("--out", type=Path, default=None, help="CSV output path")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files processed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.dir.is_dir():
        parser.error(f"Not a directory: {args.dir}")

    rows = simple_scan(args.dir, limit=args.limit)
    if args.out:
        write_rows_csv(["path", "size", "duration"], rows, args.out)
        print(f"Wrote {args.out}")
    else:
        for row in rows:
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
