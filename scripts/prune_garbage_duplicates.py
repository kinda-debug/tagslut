#!/usr/bin/env python3
"""
Prune duplicate files inside the Garbage directory to reclaim disk space.

Rules (safety-first):
1) If a duplicate group (same MD5) has at least one file outside Garbage
   (e.g., in MUSIC or Quarantine), then ALL copies inside Garbage are safe
   to delete.
2) If a group exists only inside Garbage, keep one copy in Garbage (shortest
   path then lexicographic) and delete the rest.

Dry-run by default: writes a CSV plan listing files to delete and total bytes
reclaimable. Use --commit to actually remove files and generate an executed CSV.
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from dedupe.config import load_path_config


DB_PATH = Path.home() / ".cache" / "file_dupes.db"
REPORT_DIR = Path("artifacts/reports")


@dataclass(frozen=True)
class PrunePlan:
    md5: str
    path: Path
    size: int
    reason: str  # "garbage_with_keeper_elsewhere" | "garbage_internal_extra"


def _list_groups(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_md5
        FROM file_hashes
        GROUP BY file_md5
        HAVING COUNT(*) > 1
        """
    )
    return [row[0] for row in cur.fetchall()]


def _paths_for_md5_with_size(
    conn: sqlite3.Connection, md5: str
) -> List[Tuple[Path, int]]:
    cur = conn.cursor()
    cur.execute(
        (
            "SELECT file_path, COALESCE(file_size, 0) FROM file_hashes "
            "WHERE file_md5 = ? ORDER BY file_path"
        ),
        (md5,),
    )
    return [(Path(row[0]), int(row[1] or 0)) for row in cur.fetchall()]


def _choose_keeper(paths: Sequence[Path]) -> Path:
    return sorted(paths, key=lambda p: (len(p.parts), str(p)))[0]


def build_prune_plan(
    conn: sqlite3.Connection,
    garbage_root: Path,
) -> List[PrunePlan]:
    md5s = _list_groups(conn)
    plans: List[PrunePlan] = []
    for md5 in md5s:
        items = _paths_for_md5_with_size(conn, md5)
        if not items:
            continue
        paths = [p for p, _ in items]
        sizes: Dict[Path, int] = {p: s for p, s in items}

        garbage_paths = [p for p in paths if (garbage_root in p.parents or p == garbage_root)]
        non_garbage_paths = [p for p in paths if p not in garbage_paths]

        if not garbage_paths:
            # Nothing in Garbage for this group → nothing to prune here
            continue

        if non_garbage_paths:
            # Safe to delete all Garbage copies
            for gp in garbage_paths:
                plans.append(
                    PrunePlan(
                        md5=md5,
                        path=gp,
                        size=sizes.get(gp, 0),
                        reason="garbage_with_keeper_elsewhere",
                    )
                )
        else:
            # Entire group is inside Garbage: keep 1, delete the rest
            keeper = _choose_keeper(garbage_paths)
            for gp in garbage_paths:
                if gp == keeper:
                    continue
                plans.append(
                    PrunePlan(
                        md5=md5,
                        path=gp,
                        size=sizes.get(gp, 0),
                        reason="garbage_internal_extra",
                    )
                )

    return plans


def write_plan(plans: Sequence[PrunePlan], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["md5", "path", "size_bytes", "reason"])
        for p in plans:
            w.writerow([p.md5, str(p.path), p.size, p.reason])


def execute_prune(plans: Iterable[PrunePlan]) -> Tuple[int, int]:
    deleted = 0
    freed = 0
    for p in plans:
        try:
            # Use os.remove to avoid shutil behavior with directories
            os.remove(p.path)
            deleted += 1
            freed += int(p.size or 0)
        except FileNotFoundError:
            # Already gone
            continue
        except OSError:
            # Skip on error; do not stop the batch
            continue
    return deleted, freed


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
            "Prune duplicate files inside Garbage based on the existing "
            "duplicate DB (safe deletion with dry-run + CSV)."
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
        help="Config TOML containing [paths] with 'garbage'",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=REPORT_DIR / "garbage_prune_plan.csv",
        help="Path to write the prune plan CSV (or executed CSV if --commit)",
    )
    ap.add_argument(
        "--commit",
        action="store_true",
        help="Actually delete files from Garbage (irreversible)",
    )

    ns = ap.parse_args()

    if not ns.db.exists():
        ap.error(f"Database not found: {ns.db}")

    paths = load_path_config(ns.config)
    garbage_root = paths.garbage_root

    conn = sqlite3.connect(ns.db)
    try:
        plans = build_prune_plan(conn, garbage_root=garbage_root)
    finally:
        conn.close()

    total = len(plans)
    total_bytes = sum(p.size for p in plans)
    if ns.commit:
        deleted, freed = execute_prune(plans)
        # Overwrite report with executed state
        write_plan(plans, ns.report)
        print(
            f"Deleted {deleted} files; freed {summarize_bytes(freed)}"
        )
    else:
        write_plan(plans, ns.report)
        print(
            f"Dry-run: would delete {total} files; free {summarize_bytes(total_bytes)}.\n"
            f"Plan: {ns.report}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
