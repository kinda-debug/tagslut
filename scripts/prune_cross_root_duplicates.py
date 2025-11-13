#!/usr/bin/env python3
"""Prune duplicate losers across MUSIC, Quarantine, and Garbage.

Removes (or plans removal of) all non-keeper files for duplicate groups found
in the SQLite DB produced by ``find_dupes_fast.py`` scans.

Modes:
  --by-md5 (default): Byte-identical duplicates (same MD5)
  --by-filename: Filename duplicates (same name, different content)
  --by-audio: Audio-identical duplicates (same audio fingerprint)

Keeper selection (deterministic & conservative):
  Pure shortest-path policy with NO root preference.
  1. Choose path with fewest path components (shortest)
  2. Lexicographic tie-breaker if multiple paths have same depth

Policy: All other paths in the group are deletion candidates regardless of
which root they reside in (Quarantine, Garbage, MUSIC, or external). This
enables a "100% absolute duplicate purge" with a single pass. Use the
dedicated ``prune_garbage_duplicates.py`` script when you only want to clean
Garbage.

Safety: Dry-run by default. Use ``--commit`` to actually delete files.
Outputs a CSV plan (or executed CSV) with per-item status.

CSV columns (dry-run):
  md5,path,size_bytes,reason,keeper
CSV columns (commit):
  md5,path,size_bytes,reason,keeper,status,error

Reasons:
  extra_quarantine   - Duplicate under Quarantine (non-keeper)
  extra_garbage      - Duplicate under Garbage (non-keeper)
  extra_music        - Rare case: a MUSIC path not chosen as keeper (tie-break)
  extra_external     - Duplicate outside the three configured roots

Statuses (commit mode): deleted | missing | error

Example (dry-run):
  python scripts/prune_cross_root_duplicates.py --db ~/.cache/file_dupes.db \
      --report artifacts/reports/cross_root_prune_plan.csv

Example (commit):
  python scripts/prune_cross_root_duplicates.py --commit \
      --report artifacts/reports/cross_root_prune_executed.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from dedupe.config import load_path_config

DB_PATH = Path.home() / ".cache" / "file_dupes.db"
REPORT_DIR = Path("artifacts/reports")


@dataclass
class CrossPruneItem:
    md5: str
    path: Path
    size: int
    keeper: Path
    # extra_quarantine | extra_garbage | extra_music | extra_external
    reason: str
    status: str | None = field(default=None)
    error: str | None = field(default=None)


def _list_duplicate_md5s(conn: sqlite3.Connection) -> List[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_md5 FROM file_hashes
        GROUP BY file_md5 HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        """
    )
    return [row[0] for row in cur.fetchall()]


def _list_duplicate_filenames(
    conn: sqlite3.Connection,
) -> dict[str, list[Path]]:
    """Find files with same basename (filename duplicates)."""
    from collections import defaultdict
    
    cur = conn.cursor()
    cur.execute("SELECT file_path FROM file_hashes")
    
    by_name: dict[str, list[Path]] = defaultdict(list)
    for (path_str,) in cur.fetchall():
        p = Path(path_str)
        by_name[p.name].append(p)
    
    # Return only groups with 2+ files
    return {name: paths for name, paths in by_name.items() if len(paths) > 1}


def _list_duplicate_audio_fingerprints(
    conn: sqlite3.Connection,
) -> dict[str, list[Path]]:
    """Find files with same audio fingerprint (audio-identical duplicates)."""
    from collections import defaultdict
    
    cur = conn.cursor()
    cur.execute(
        """
        SELECT file_path, audio_fingerprint_hash
        FROM file_hashes
        WHERE audio_fingerprint_hash IS NOT NULL
        """
    )
    
    by_fp: dict[str, list[Path]] = defaultdict(list)
    for path_str, fp_hash in cur.fetchall():
        p = Path(path_str)
        by_fp[fp_hash].append(p)
    
    # Return only groups with 2+ files
    return {
        fp_hash: paths
        for fp_hash, paths in by_fp.items()
        if len(paths) > 1
    }


def _paths_for_md5_with_sizes(
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


def choose_keeper(
    paths: Sequence[Path], library_root: Optional[Path] = None
) -> Path:
    """Return deterministic keeper path for a duplicate group.
    
    Policy: Pure shortest-path selection with NO root preference.
    Selects path with fewest components, lexicographic tie-breaker.
    
    Args:
        paths: Candidate paths for keeper selection
        library_root: Ignored (kept for backward compatibility)
    """
    return sorted(paths, key=lambda p: (len(p.parts), str(p)))[0]


def classify_reason(
    path: Path,
    library_root: Path,
    quarantine_root: Path,
    garbage_root: Path,
    keeper: Path,
) -> str:
    if path == keeper:
        raise ValueError("classify_reason called with keeper path")
    if library_root in path.parents or path == library_root:
        return "extra_music"
    if quarantine_root in path.parents or path == quarantine_root:
        return "extra_quarantine"
    if garbage_root in path.parents or path == garbage_root:
        return "extra_garbage"
    return "extra_external"


def build_cross_root_prune_plan(
    conn: sqlite3.Connection,
    library_root: Path,
    quarantine_root: Path,
    garbage_root: Path,
) -> List[CrossPruneItem]:
    """Build deletion plan across all three roots (dry-run data structure)."""
    md5s = _list_duplicate_md5s(conn)
    plan: List[CrossPruneItem] = []
    for md5 in md5s:
        rows = _paths_for_md5_with_sizes(conn, md5)
        if not rows:
            continue
        paths = [p for p, _ in rows]
        sizes = {p: s for p, s in rows}
        keeper = choose_keeper(paths, library_root)
        for p in paths:
            if p == keeper:
                continue
            reason = classify_reason(
                p, library_root, quarantine_root, garbage_root, keeper
            )
            plan.append(
                CrossPruneItem(
                    md5=md5,
                    path=p,
                    size=sizes.get(p, 0),
                    keeper=keeper,
                    reason=reason,
                )
            )
    return plan


def build_filename_prune_plan(
    conn: sqlite3.Connection,
    library_root: Path,
    quarantine_root: Path,
    garbage_root: Path,
) -> List[CrossPruneItem]:
    """Build deletion plan for filename duplicates (same name, different
    content).
    """
    filename_groups = _list_duplicate_filenames(conn)
    plan: List[CrossPruneItem] = []
    
    # Get file sizes
    cur = conn.cursor()
    cur.execute("SELECT file_path, COALESCE(file_size, 0) FROM file_hashes")
    sizes = {Path(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    
    for filename, paths in filename_groups.items():
        keeper = choose_keeper(paths, library_root)
        for p in paths:
            if p == keeper:
                continue
            reason = classify_reason(
                p, library_root, quarantine_root, garbage_root, keeper
            )
            plan.append(
                CrossPruneItem(
                    md5=f"filename:{filename}",  # Use filename as identifier
                    path=p,
                    size=sizes.get(p, 0),
                    keeper=keeper,
                    reason=reason,
                )
            )
    return plan


def build_audio_prune_plan(
    conn: sqlite3.Connection,
    library_root: Path,
    quarantine_root: Path,
    garbage_root: Path,
) -> List[CrossPruneItem]:
    """Build deletion plan for audio fingerprint duplicates (audio-identical
    files).
    """
    audio_groups = _list_duplicate_audio_fingerprints(conn)
    plan: List[CrossPruneItem] = []
    
    # Get file sizes
    cur = conn.cursor()
    cur.execute("SELECT file_path, COALESCE(file_size, 0) FROM file_hashes")
    sizes = {Path(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    
    for fp_hash, paths in audio_groups.items():
        keeper = choose_keeper(paths, library_root)
        for p in paths:
            if p == keeper:
                continue
            reason = classify_reason(
                p, library_root, quarantine_root, garbage_root, keeper
            )
            plan.append(
                CrossPruneItem(
                    md5=f"audio:{fp_hash[:16]}",  # Use audio FP as ID
                    path=p,
                    size=sizes.get(p, 0),
                    keeper=keeper,
                    reason=reason,
                )
            )
    return plan


def execute_plan(
    items: Iterable[CrossPruneItem],
) -> Tuple[int, int, List[CrossPruneItem]]:
    deleted = 0
    freed = 0
    executed: List[CrossPruneItem] = []
    for item in items:
        try:
            os.remove(item.path)
            item.status = "deleted"
            item.error = None
            deleted += 1
            freed += int(item.size or 0)
        except FileNotFoundError:
            item.status = "missing"
            item.error = None
        except OSError as e:
            item.status = "error"
            item.error = str(e)
        executed.append(item)
    return deleted, freed, executed


def _fmt_bytes(n: int) -> str:
    gib = n / (1024 ** 3)
    mib = n / (1024 ** 2)
    if gib >= 1:
        return f"{gib:.2f} GiB"
    if mib >= 1:
        return f"{mib:.2f} MiB"
    return f"{n} B"


def write_csv(
    items: Sequence[CrossPruneItem], path: Path, include_status: bool
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if include_status:
            w.writerow([
                "md5",
                "path",
                "size_bytes",
                "reason",
                "keeper",
                "status",
                "error",
            ])
            for i in items:
                w.writerow([
                    i.md5,
                    str(i.path),
                    i.size,
                    i.reason,
                    str(i.keeper),
                    i.status or "",
                    i.error or "",
                ])
        else:
            w.writerow(["md5", "path", "size_bytes", "reason", "keeper"])
            for i in items:
                w.writerow([
                    i.md5,
                    str(i.path),
                    i.size,
                    i.reason,
                    str(i.keeper),
                ])


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Plan (or execute) deletion of duplicate losers across MUSIC, "
            "Quarantine, and Garbage using the duplicate DB."
        )
    )
    ap.add_argument("--db", type=Path, default=DB_PATH, help="SQLite DB path")
    ap.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Config TOML with path roots",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=REPORT_DIR / "cross_root_prune_plan.csv",
        help="Path for plan/executed CSV",
    )
    ap.add_argument(
        "--commit", action="store_true", help="Actually delete files"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of deletions to perform (commit mode only)",
    )
    
    # Mode selection
    mode_group = ap.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--by-md5",
        action="store_true",
        default=True,
        help="Delete MD5 duplicates (byte-identical) [default]",
    )
    mode_group.add_argument(
        "--by-filename",
        action="store_true",
        help="Delete filename duplicates (same name, different content)",
    )
    mode_group.add_argument(
        "--by-audio",
        action="store_true",
        help="Delete audio fingerprint duplicates (audio-identical)",
    )

    ns = ap.parse_args()

    if not ns.db.exists():
        ap.error(f"Database not found: {ns.db}")

    paths = load_path_config(ns.config)
    conn = sqlite3.connect(ns.db)
    try:
        if ns.by_audio:
            plan = build_audio_prune_plan(
                conn,
                library_root=paths.library_root,
                quarantine_root=paths.quarantine_root,
                garbage_root=paths.garbage_root,
            )
        elif ns.by_filename:
            plan = build_filename_prune_plan(
                conn,
                library_root=paths.library_root,
                quarantine_root=paths.quarantine_root,
                garbage_root=paths.garbage_root,
            )
        else:
            plan = build_cross_root_prune_plan(
                conn,
                library_root=paths.library_root,
                quarantine_root=paths.quarantine_root,
                garbage_root=paths.garbage_root,
            )
    finally:
        conn.close()

    total_bytes = sum(i.size for i in plan)
    if ns.commit:
        exec_items = plan
        if ns.limit is not None and ns.limit >= 0:
            exec_items = plan[: ns.limit]
        deleted, freed, executed = execute_plan(exec_items)
        write_csv(executed, ns.report, include_status=True)
        remaining = max(0, len(plan) - deleted) if ns.limit else 0
        print(
            (
                "Deleted {} files (limit {}). Freed {}. Remaining not "
                "executed: {}. Executed CSV: {}"
            ).format(
                deleted,
                ns.limit if ns.limit is not None else "none",
                _fmt_bytes(freed),
                remaining,
                ns.report,
            )
        )
    else:
        write_csv(plan, ns.report, include_status=False)
        print(
            "Dry-run: would delete {} files; free {}. Plan: {}".format(
                len(plan), _fmt_bytes(total_bytes), ns.report
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
