#!/usr/bin/env python3
"""Run read-only structural checks for a standalone v3 database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from urllib.parse import quote

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.db.v3.doctor import doctor_v3


def _connect_ro(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"v3 DB not found: {resolved}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v3 DB doctor checks")
    parser.add_argument("--v3", required=True, type=Path, help="Path to v3 DB")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with _connect_ro(args.v3) as conn:
            result = doctor_v3(conn)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    counts = result["counts"]
    print(f"v3 db: {args.v3.expanduser().resolve()}")
    print(f"foreign_keys: {result['foreign_keys']}")
    print(f"asset_file_total: {counts['asset_file_total']}")
    print(f"asset_link_total: {counts['asset_link_total']}")
    print(f"track_identity_total: {counts['track_identity_total']}")
    print(f"integrity_done: {counts['integrity_done']}")
    print(f"sha256_done: {counts['sha256_done']}")
    print(f"enriched_done: {counts['enriched_done']}")

    if not result["ok"]:
        print("FAILED:")
        for error in result["errors"]:
            print(f"- {error}")
        return 1

    print("OK: v3 doctor checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

