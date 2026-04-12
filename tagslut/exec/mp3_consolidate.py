from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Source:
    root: Path
    prefix: str


@dataclass
class Stats:
    sources_processed: int = 0
    files_moved: int = 0
    duplicates_removed: int = 0
    conflicts_renamed: int = 0
    db_rows_updated: int = 0
    failed: int = 0


DEFAULT_MP3_LIBRARY = Path("/Volumes/MUSIC/MP3_LIBRARY")
DEFAULT_SOURCES: Sequence[Source] = (
    Source(Path("/Volumes/MUSIC/DJ_LIBRARY"), "_legacy_dj"),
    Source(Path("/Volumes/MUSIC/DJ_POOL_MANUAL_MP3"), "_legacy_manual"),
    Source(Path("/Volumes/MUSIC/imindeepshit"), "_imindeepshit"),
    Source(Path("/Volumes/MUSIC/_work/gig_runs"), "_gig_runs"),
    Source(Path("/Volumes/MUSIC/tmp"), "_tmp_mp3"),
)


def _iter_mp3(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink():
            continue
        if path.suffix.lower() != ".mp3":
            continue
        yield path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visible_files_exist(root: Path) -> bool:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        return True
    return False


def _next_conflict_path(dest: Path) -> Path:
    candidate = dest.with_name(f"{dest.stem}_conflict{dest.suffix}")
    if not candidate.exists():
        return candidate
    i = 2
    while True:
        candidate = dest.with_name(f"{dest.stem}_conflict{i}{dest.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def _update_db_path(conn: sqlite3.Connection, src: Path, dest: Path) -> int:
    before = conn.total_changes
    conn.execute("UPDATE files SET path = ? WHERE path = ?", (str(dest), str(src)))
    return conn.total_changes - before


def consolidate_mp3s(
    *,
    mp3_library: Path,
    sources: Sequence[Source],
    db_path: Path | None,
    execute: bool,
    verbose: bool,
) -> Stats:
    mp3_library = mp3_library.expanduser().resolve()
    stats = Stats()

    conn: sqlite3.Connection | None = None
    if execute:
        if db_path is None:
            env_db = os.environ.get("TAGSLUT_DB")
            if not env_db:
                raise RuntimeError("--db not provided and TAGSLUT_DB not set")
            db_path = Path(env_db)
        db_path = db_path.expanduser().resolve()
        conn = sqlite3.connect(str(db_path))

    try:
        for source in sources:
            source_root = source.root.expanduser().resolve()
            if not source_root.is_dir():
                continue
            stats.sources_processed += 1

            for src in _iter_mp3(source_root):
                try:
                    src = src.resolve()
                    if mp3_library in src.parents:
                        continue

                    rel = src.relative_to(source_root)
                    dest = (mp3_library / source.prefix / rel).resolve()

                    if not execute:
                        print(f"WOULD MOVE: {src} \u2192 {dest}")
                        continue

                    assert conn is not None
                    dest.parent.mkdir(parents=True, exist_ok=True)

                    if dest.exists():
                        if _sha256(src) == _sha256(dest):
                            src.unlink()
                            stats.duplicates_removed += 1
                            stats.db_rows_updated += _update_db_path(conn, src, dest)
                            if verbose:
                                print(f"DUPLICATE: {src} == {dest} (deleted src)")
                            continue

                        conflict_dest = _next_conflict_path(dest)
                        shutil.move(str(dest), str(conflict_dest))
                        stats.conflicts_renamed += 1
                        stats.db_rows_updated += _update_db_path(conn, dest, conflict_dest)
                        if verbose:
                            print(f"CONFLICT: renamed {dest} \u2192 {conflict_dest}")

                    shutil.move(str(src), str(dest))
                    stats.files_moved += 1
                    stats.db_rows_updated += _update_db_path(conn, src, dest)
                    if verbose:
                        print(f"MOVED: {src} \u2192 {dest}")
                except Exception as exc:  # noqa: BLE001
                    stats.failed += 1
                    print(f"FAILED: {src} ({exc})")

        if execute and conn is not None:
            conn.commit()
    finally:
        if conn is not None:
            conn.close()

    print("MP3 Consolidation complete:")
    print(f"  Sources processed: {stats.sources_processed}")
    print(f"  Files moved:       {stats.files_moved}")
    print(f"  Duplicates removed:{stats.duplicates_removed}")
    print(f"  Conflicts renamed: {stats.conflicts_renamed}")
    print(f"  DB rows updated:   {stats.db_rows_updated}")
    print(f"  Failed:            {stats.failed}")

    for source in sources:
        source_root = source.root.expanduser().resolve()
        if not source_root.is_dir():
            continue
        if not _visible_files_exist(source_root):
            print(f"  Empty after move (can delete): {source_root}")

    return stats


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Move scattered MP3s into /Volumes/MUSIC/MP3_LIBRARY and update DB.")
    parser.add_argument("--db", type=Path, default=None, help="Database path (reads $TAGSLUT_DB if not provided).")
    parser.add_argument("--execute", action="store_true", help="Actually move files and update DB (default: dry-run).")
    parser.add_argument("--verbose", action="store_true", help="Print one line per file moved.")
    args = parser.parse_args(argv)

    consolidate_mp3s(
        mp3_library=DEFAULT_MP3_LIBRARY,
        sources=DEFAULT_SOURCES,
        db_path=args.db,
        execute=bool(args.execute),
        verbose=bool(args.verbose),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

