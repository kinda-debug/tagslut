#!/usr/bin/env python3
"""
best_by_quality.py

Phase 2: quality-based selection.

- Reads artifacts/db/library.db (table library_files).
- Reads artifacts/reports/hash_prune_decisions.csv and restricts to rows marked KEEP.
- For those KEEP paths:
    - Groups by filename stem (case-insensitive, without extension).
    - Ignores lossy codecs (mp3, m4a, aac, ogg, wma, opus).
    - Scores candidates and picks a single KEEP per group based on:

        extension priority: flac > alac > wav/aiff > others
        path priority: REPAIRED > NEW_LIBRARY/MUSIC > NEW_LIBRARY > others
        sample_rate, bit_depth, channels, duration, size_bytes

- Writes artifacts/reports/quality_prune_decisions.csv with:

    group_id,path,action,reason,score,extension,sample_rate,bit_depth,channels,duration,size_bytes

Run AFTER best_by_hash.py, and use the resulting CSV as input.
"""

import csv
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


DEFAULT_DB = Path("artifacts/db/library.db")
DEFAULT_HASH_DECISIONS = Path("artifacts/reports/hash_prune_decisions.csv")
DEFAULT_OUT = Path("artifacts/reports/quality_prune_decisions.csv")


LOSSY_EXTENSIONS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".wma",
    ".opus",
}


@dataclass
class QualityEntry:
    path: str
    sample_rate: Optional[int]
    bit_depth: Optional[int]
    channels: Optional[int]
    duration: Optional[float]
    size_bytes: int


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def extension_priority(path: str) -> int:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".flac":
        return 5
    if ext in (".alac", ".m4b"):
        return 4
    if ext in (".wav", ".aiff", ".aif"):
        return 3
    if ext in LOSSY_EXTENSIONS:
        return 0
    return 1


def path_priority(path: str) -> int:
    p = path
    score = 0

    if "/NEW_LIBRARY/MUSIC/REPAIRED/" in p:
        score += 6
    elif "/NEW_LIBRARY/MUSIC/" in p:
        score += 5
    elif "/NEW_LIBRARY/" in p:
        score += 4

    if "repairedforreal" in p:
        score += 3

    junk_tokens = [
        "Quarantine",
        "Garbage",
        "_quarantine",
        "_trash",
        "_TRASH_DUPES",
    ]
    for t in junk_tokens:
        if t in p:
            score -= 4

    return score


def is_lossy(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in LOSSY_EXTENSIONS


def quality_score(e: QualityEntry) -> float:
    ext_score = extension_priority(e.path)
    path_score = path_priority(e.path)

    sr = (e.sample_rate or 0)
    bd = (e.bit_depth or 0)
    ch = (e.channels or 0)
    dur = (e.duration or 0.0)
    size = e.size_bytes or 0

    # Basic scoring: extension + path dominate; tech params refine.
    score = (
        ext_score * 1_000_000
        + path_score * 50_000
        + (sr / 1000.0) * 200
        + bd * 50
        + ch * 25
        + (dur / 60.0) * 10
        + size / (1024.0 * 1024.0)  # MB as small tie-breaker
    )
    return score


def load_keep_paths_from_hash(csv_path: Path) -> List[str]:
    keep_paths: List[str] = []
    if not csv_path.exists():
        return keep_paths

    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = (row.get("action") or "").strip().upper()
            path = (row.get("path") or "").strip()
            if action == "KEEP" and path:
                keep_paths.append(path)
    return keep_paths


def load_quality_entries(db_path: Path, allowed_paths: List[str]) -> List[QualityEntry]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT path, sample_rate, bit_depth, channels, duration, size_bytes
            FROM library_files
            """
        ).fetchall()
    finally:
        conn.close()

    allowed_set = set(allowed_paths) if allowed_paths else None

    entries: List[QualityEntry] = []
    for row in rows:
        path = row["path"]
        if allowed_set is not None and path not in allowed_set:
            continue
        if is_lossy(path):
            # Ignore lossy in quality phase
            continue

        entries.append(
            QualityEntry(
                path=path,
                sample_rate=row["sample_rate"],
                bit_depth=row["bit_depth"],
                channels=row["channels"],
                duration=row["duration"],
                size_bytes=row["size_bytes"] or 0,
            )
        )

    return entries


def group_key(path: str) -> str:
    """
    Simple grouping key: lowercase filename stem.
    """
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    return stem.lower()


def main() -> None:
    db_path = DEFAULT_DB
    hash_decisions = DEFAULT_HASH_DECISIONS
    out_path = DEFAULT_OUT

    ensure_parent(out_path)

    keep_paths = load_keep_paths_from_hash(hash_decisions)
    entries = load_quality_entries(db_path, keep_paths)

    # Group by filename stem
    groups: Dict[str, List[QualityEntry]] = {}
    for e in entries:
        k = group_key(e.path)
        groups.setdefault(k, []).append(e)

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "group_id",
                "path",
                "action",
                "reason",
                "score",
                "extension",
                "sample_rate",
                "bit_depth",
                "channels",
                "duration",
                "size_bytes",
            ]
        )

        for gid, group in groups.items():
            if not group:
                continue
            if len(group) == 1:
                e = group[0]
                writer.writerow(
                    [
                        gid,
                        e.path,
                        "KEEP",
                        "only_candidate",
                        quality_score(e),
                        os.path.splitext(e.path)[1].lower(),
                        e.sample_rate or "",
                        e.bit_depth or "",
                        e.channels or "",
                        e.duration or "",
                        e.size_bytes,
                    ]
                )
                continue

            scores = [quality_score(e) for e in group]
            keeper_idx = max(range(len(group)), key=lambda i: scores[i])

            for idx, e in enumerate(group):
                action = "KEEP" if idx == keeper_idx else "MOVE"
                reason = "best_by_quality" if action == "KEEP" else "lower_quality_candidate"
                writer.writerow(
                    [
                        gid,
                        e.path,
                        action,
                        reason,
                        scores[idx],
                        os.path.splitext(e.path)[1].lower(),
                        e.sample_rate or "",
                        e.bit_depth or "",
                        e.channels or "",
                        e.duration or "",
                        e.size_bytes,
                    ]
                )

    print(f"Wrote quality-based decisions to: {out_path}")


if __name__ == "__main__":
    main()
