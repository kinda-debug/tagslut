#!/usr/bin/env python3
"""Create a standalone v3 music database."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow direct script execution from repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tagslut.storage.v3.db import open_db_v3
from tagslut.storage.v3.schema import create_schema_v3


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a v3 music SQLite database.")
    parser.add_argument("--out", required=True, type=Path, help="Output DB path")
    args = parser.parse_args()

    out_path = args.out.expanduser().resolve()
    conn = open_db_v3(out_path, create=True)
    try:
        create_schema_v3(conn)
    finally:
        conn.close()

    print(f"Created v3 DB: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
