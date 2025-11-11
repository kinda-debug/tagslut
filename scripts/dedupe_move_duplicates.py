#!/usr/bin/env python3
"""
Move byte-identical duplicates to the configured Garbage directory using the
SQLite database produced by scripts/find_dupes_fast.py.

Safety-first: runs in dry-run mode by default. Use --commit to actually move
files. The keeper for each duplicate group is chosen deterministically and
conservatively.

Keeper selection heuristic (in order):
  1) Prefer the path with the shortest length (fewer subdirectories)
  2) If tie, prefer the lexicographically first path

This script preserves the relative path from the library root when moving to
Garbage, creating parent directories as needed. Name collisions in Garbage are
resolved by appending a ".dupe-{n}" suffix to the filename stem.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from dedupe.config import load_path_config


DB_PATH = Path.home() / ".cache" / "file_dupes.db"
REPORT_DIR = Path("artifacts/reports")


@dataclass(frozen=True)
class MovePlan:
    md5: str
    keeper: Path
    source: Path
    destination: Path


def _list_duplicate_groups(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_md5
        FROM file_hashes
        GROUP BY file_md5
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        """
    )
    return [row[0] for row in cur.fetchall()]


def _paths_for_md5(conn: sqlite3.Connection, md5: str) -> List[Path]:
    cur = conn.cursor()
    cur.execute(
        (
            "SELECT file_path FROM file_hashes "
            "WHERE file_md5 = ? ORDER BY file_path"
        ),
        (md5,),
    )
    return [Path(row[0]) for row in cur.fetchall()]


def _choose_keeper(paths: Sequence[Path], library_root: Path) -> Path:
    """Return keeper for a duplicate group.

    Preference order:
    1. Any path under the configured library_root (Music). If multiple, choose
       shortest (fewest components) then lexicographically.
    2. Otherwise, global shortest + lexicographic.
    """

    library_candidates = [
        p for p in paths if (library_root in p.parents or p == library_root)
    ]
    if library_candidates:
        return sorted(
            library_candidates, key=lambda p: (len(p.parts), str(p))
        )[0]
    return sorted(paths, key=lambda p: (len(p.parts), str(p)))[0]


def _unique_destination(base: Path) -> Path:
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    n = 1
    while True:
        candidate = parent / f"{stem}.dupe-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def plan_moves(
    conn: sqlite3.Connection,
    library_root: Path,
    quarantine_root: Path,
    garbage_root: Path,
    limit_groups: int | None = None,
) -> List[MovePlan]:
    md5_list = _list_duplicate_groups(conn)
    if limit_groups is not None:
        md5_list = md5_list[: max(0, limit_groups)]

    plans: List[MovePlan] = []
    for md5 in md5_list:
        paths = _paths_for_md5(conn, md5)
        if not paths:
            continue
        keeper = _choose_keeper(paths, library_root)
        for src in paths:
            if src == keeper:
                continue
            # Skip moving files that already reside under Garbage; we don't
            # shuffle Garbage-to-Garbage in this phase.
            if garbage_root in src.parents or src == garbage_root:
                continue
            try:
                # Prefer preserving relative structure from the source root
                if library_root in src.parents or src == library_root:
                    rel = src.relative_to(library_root)
                elif quarantine_root in src.parents or src == quarantine_root:
                    rel = Path("quarantine") / src.relative_to(quarantine_root)
                else:
                    rel = Path("_external") / src.name
            except ValueError:
                rel = Path("_external") / src.name

            dest = garbage_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest = _unique_destination(dest)
            plans.append(
                MovePlan(md5=md5, keeper=keeper, source=src, destination=dest)
            )
    return plans


def execute_moves(
    plans: Iterable[MovePlan], commit: bool = False
) -> Tuple[int, int]:
    moved = 0
    skipped = 0
    for plan in plans:
        if not plan.source.exists():
            skipped += 1
            continue
        if commit:
            try:
                plan.destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(plan.source), str(plan.destination))
                moved += 1
            except OSError:
                skipped += 1
        else:
            # Dry-run: no-op
            skipped += 1
    return moved, skipped


def write_report(plans: Sequence[MovePlan], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["md5", "keeper", "source", "destination"])
        for p in plans:
            writer.writerow([
                p.md5,
                str(p.keeper),
                str(p.source),
                str(p.destination),
            ])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Move duplicate files (byte-identical) discovered by "
            "find_dupes_fast.py into the configured Garbage directory."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help="Path to SQLite database populated by find_dupes_fast.py",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to configuration file defining library and garbage roots",
    )
    parser.add_argument(
        "--limit-groups",
        type=int,
        default=None,
        help="Only process the first N duplicate groups (useful for testing)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=REPORT_DIR / "planned_moves.csv",
        help="Path to write the planned (or executed) move report CSV",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually move files (otherwise dry-run)",
    )

    ns = parser.parse_args()

    paths = load_path_config(Path("config.toml"))
    library_root = paths.library_root
    quarantine_root = paths.quarantine_root
    garbage_root = paths.garbage_root

    if not ns.db.exists():
        parser.error(f"Database not found: {ns.db}")

    conn = sqlite3.connect(ns.db)
    try:
        plans = plan_moves(
            conn,
            library_root=library_root,
            quarantine_root=quarantine_root,
            garbage_root=garbage_root,
            limit_groups=ns.limit_groups,
        )
    finally:
        conn.close()

    write_report(plans, ns.report)

    if ns.commit:
        moved, skipped = execute_moves(plans, commit=True)
        print(f"Moved {moved} files; {skipped} skipped or failed")
    else:
        print(
            f"Dry-run: {len(plans)} planned moves written to {ns.report}. "
            "Re-run with --commit to apply."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
