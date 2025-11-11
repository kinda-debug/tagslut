#!/usr/bin/env python3
"""
Prune stale rows from the duplicate DB for files that no longer exist on disk.

Why: After external deletions (e.g., Garbage pruning), the SQLite DB may still
contain entries for paths that have been removed. This script reconciles the DB
with the filesystem so subsequent reports/plans reflect reality without a full
rescan.

Behavior:
- By default, only checks/removes rows under the configured Garbage root.
- Use --scope all to scan all rows in the DB (slower on large DBs).
- Writes a CSV report of removed rows for auditing.

Usage examples:
  python scripts/db_prune_missing_files.py \
    --db ~/.cache/file_dupes.db \
    --config config.toml \
    --report artifacts/reports/db_prune_missing.csv

  # Broader cleanup across all paths (MUSIC, Quarantine, Garbage):
  python scripts/db_prune_missing_files.py --scope all
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List

from dedupe.config import load_path_config


DB_PATH = Path.home() / ".cache" / "file_dupes.db"
REPORT_DIR = Path("artifacts/reports")


@dataclass(frozen=True)
class Row:
    path: str
    md5: str
    size: int


def iter_rows(conn: sqlite3.Connection, prefix: str | None) -> Iterator[Row]:
    cur = conn.cursor()
    if prefix:
        like = prefix.rstrip("/") + "/%"
        cur.execute(
            (
                "SELECT file_path, file_md5, COALESCE(file_size, 0) "
                "FROM file_hashes WHERE file_path LIKE ?"
            ),
            (like,),
        )
    else:
        cur.execute(
            "SELECT file_path, file_md5, COALESCE(file_size, 0) "
            "FROM file_hashes"
        )
    for path, md5, size in cur.fetchall():
        yield Row(path=path, md5=md5, size=int(size or 0))


def prune_missing(conn: sqlite3.Connection, rows: Iterable[Row]) -> List[Row]:
    removed: List[Row] = []
    cur = conn.cursor()
    for r in rows:
        if not os.path.exists(r.path):
            cur.execute(
                "DELETE FROM file_hashes WHERE file_path = ?",
                (r.path,),
            )
            removed.append(r)
    conn.commit()
    return removed


def write_report(removed: List[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["md5", "path", "size_bytes"])  # simple audit log
        for r in removed:
            w.writerow([r.md5, r.path, r.size])


def summarize_bytes(n: int) -> str:
    gib = n / (1024 ** 3)
    mib = n / (1024 ** 2)
    if gib >= 1:
        return f"{gib:.2f} GiB"
    if mib >= 1:
        return f"{mib:.2f} MiB"
    return f"{n} B"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Remove DB rows pointing to files that no longer exist. Default: "
            "only under Garbage root; use --scope all for full DB."
        )
    )
    ap.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="SQLite DB file produced by find_dupes_fast.py",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Config TOML containing [paths] with 'garbage' root",
    )
    ap.add_argument(
        "--scope",
        choices=["garbage", "all"],
        default="garbage",
        help="Limit cleanup to Garbage paths or scan all DB rows",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=REPORT_DIR / "db_prune_missing.csv",
        help="Path to write a CSV of removed rows",
    )

    ns = ap.parse_args()

    if not ns.db.exists():
        ap.error(f"Database not found: {ns.db}")

    paths = load_path_config(ns.config)
    prefix: str | None
    if ns.scope == "garbage":
        prefix = str(paths.garbage_root)
    else:
        prefix = None

    conn = sqlite3.connect(ns.db)
    try:
        rows = list(iter_rows(conn, prefix=prefix))
        removed = prune_missing(conn, rows)
    finally:
        conn.close()

    total_bytes = sum(r.size for r in removed)
    write_report(removed, ns.report)
    print(
        (
            "Removed {} stale DB rows (scope: {}). Size referenced: {}. "
            "Report: {}"
        ).format(
            len(removed),
            ns.scope,
            summarize_bytes(total_bytes),
            ns.report,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
