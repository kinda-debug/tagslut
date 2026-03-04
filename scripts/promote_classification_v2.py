#!/usr/bin/env python3
"""Promote files.classification_v2 -> files.classification in a SQLite DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure local package imports resolve when running as a standalone script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.classification_promotion import (  # noqa: E402
    PromotionError,
    format_promotion_result,
    promote_classification_v2,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote classification_v2 to the primary classification column."
    )
    parser.add_argument("--db", required=True, help="Path to inventory SQLite DB")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show promotion plan without modifying the database",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = promote_classification_v2(Path(args.db), dry_run=bool(args.dry_run))
    except PromotionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for line in format_promotion_result(result):
        print(line)
    if result.status == "dry_run":
        print("Dry-run only: no database changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
