#!/usr/bin/env python3

import argparse
import os
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from pyrekordbox import Rekordbox6Database
from pyrekordbox.db6.tables import DjmdContent


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}
HEX_PREFIX_RE = re.compile(r"^[0-9A-Fa-f]{8}_")


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite live Rekordbox DB track paths to files found under a centralized "
            "POOL_LIBRARY."
        )
    )
    parser.add_argument("db_path", help="Path to the live Rekordbox master.db")
    parser.add_argument("pool_root", help="Path to the centralized POOL_LIBRARY root")
    parser.add_argument(
        "--report",
        help="Optional path for an unresolved/ambiguous match report",
    )
    parser.add_argument(
        "--backup-dir",
        help="Optional backup directory. Defaults to a timestamped folder next to the DB.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate changes without writing to the DB",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-track rewrite decisions",
    )
    return parser.parse_args()


def verbose_print(enabled, message):
    if enabled:
        print(message)


def score_path(path):
    score = 0
    name = path.name
    if "__conflict" in name:
        score -= 100
    if HEX_PREFIX_RE.match(name):
        score -= 10
    if any(part.startswith(".") for part in path.parts):
        score -= 5
    return score


def index_pool(pool_root):
    by_size = defaultdict(list)
    by_size_basename = defaultdict(list)
    counts = Counter()

    for dirpath, dirnames, filenames in os.walk(pool_root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        current_root = Path(dirpath)
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = current_root / filename
            if path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            by_size[size].append(path)
            by_size_basename[(size, path.name)].append(path)
            counts["audio_files"] += 1

    return by_size, by_size_basename, counts


def choose_match(row, by_size, by_size_basename):
    try:
        size = int(row.FileSize)
    except (TypeError, ValueError):
        return None, "missing_size", []

    basename = Path(row.FolderPath).name if row.FolderPath else ""
    exact_matches = by_size_basename.get((size, basename), [])
    if len(exact_matches) == 1:
        return exact_matches[0], "size_basename_unique", exact_matches

    size_matches = by_size.get(size, [])
    if not size_matches:
        return None, "no_size_match", []

    if len(size_matches) == 1:
        return size_matches[0], "size_unique", size_matches

    best_score = max(score_path(path) for path in size_matches)
    best_paths = [path for path in size_matches if score_path(path) == best_score]
    if len(best_paths) == 1:
        return best_paths[0], "heuristic_unique", size_matches

    return None, "ambiguous", size_matches


def backup_database(db_path, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(db_path) + suffix)
        if source.exists():
            target = backup_dir / source.name
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def write_report(report_path, unresolved_rows):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        for row in unresolved_rows:
            handle.write(
                f"[{row['track_id']}] {row['artist']} - {row['title']} :: {row['reason']}\n"
            )
            for candidate in row["candidates"]:
                handle.write(f"  {candidate}\n")


def main():
    args = parse_args()

    db_path = Path(args.db_path).expanduser()
    pool_root = Path(args.pool_root).expanduser()
    report_path = (
        Path(args.report).expanduser()
        if args.report
        else db_path.with_name(db_path.name + ".pool_rewrite.unresolved.txt")
    )

    if args.backup_dir:
        backup_dir = Path(args.backup_dir).expanduser()
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = db_path.parent / f"pool_path_rewrite_backup_{timestamp}"

    by_size, by_size_basename, pool_counts = index_pool(pool_root)
    db = Rekordbox6Database(path=db_path)

    rows = db.session.query(DjmdContent).all()
    stats = Counter()
    unresolved_rows = []

    for row in rows:
        stats["rows_scanned"] += 1
        if not row.FolderPath:
            stats["empty_path"] += 1
            continue

        match, reason, candidates = choose_match(row, by_size, by_size_basename)
        stats[reason] += 1

        if match is None:
            unresolved_rows.append(
                {
                    "track_id": row.ID,
                    "artist": getattr(row, "SrcArtistName", "") or "",
                    "title": row.Title or "",
                    "reason": reason,
                    "candidates": [str(path) for path in candidates[:10]],
                }
            )
            verbose_print(
                args.verbose,
                f"leave unchanged [{row.ID}] {row.Title} :: {reason}",
            )
            continue

        new_path = str(match)
        if row.FolderPath == new_path and row.FileNameL == match.name:
            stats["already_correct"] += 1
            continue

        row.FolderPath = new_path
        row.FileNameL = match.name
        stats["rows_rewritten"] += 1
        verbose_print(
            args.verbose,
            f"rewrite [{row.ID}] {row.Title} -> {new_path}",
        )

    if not args.dry_run:
        copied = backup_database(db_path, backup_dir)
        db.commit()
        write_report(report_path, unresolved_rows)
    else:
        copied = []
        db.close()

    print("Summary")
    print(f"- DB path: {db_path}")
    print(f"- POOL_LIBRARY: {pool_root}")
    print(f"- Pool audio files indexed: {pool_counts['audio_files']}")
    print(f"- Rows scanned: {stats['rows_scanned']}")
    print(f"- Rows rewritten: {stats['rows_rewritten']}")
    print(f"- Already correct: {stats['already_correct']}")
    print(f"- Unique by size: {stats['size_unique']}")
    print(f"- Unique by size+basename: {stats['size_basename_unique']}")
    print(f"- Unique by heuristic: {stats['heuristic_unique']}")
    print(f"- Ambiguous: {stats['ambiguous']}")
    print(f"- No size match: {stats['no_size_match']}")
    print(f"- Missing size: {stats['missing_size']}")
    print(f"- Empty path: {stats['empty_path']}")
    if args.dry_run:
        print("- Mode: dry-run")
    else:
        print(f"- Backup dir: {backup_dir}")
        print(f"- Backup files: {len(copied)}")
        print(f"- Unresolved report: {report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
