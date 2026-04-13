from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


AUDIO_EXTS = {
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".wav",
    ".aif",
    ".aiff",
    ".ogg",
    ".opus",
    ".wma",
}


@dataclass
class Summary:
    total_audio_files: int = 0
    conflicts_dest_exists: int = 0
    format_mp3: int = 0
    format_m4a: int = 0
    format_other: int = 0

    files_moved: int = 0
    files_skipped_identical: int = 0
    files_moved_to_conflicts: int = 0
    db_rows_updated: int = 0
    dirs_removed: int = 0
    failed: int = 0


def _is_mounted(path: Path) -> bool:
    return os.path.ismount(str(path))


def _volume_mountpoint(path: Path) -> Path | None:
    try:
        parts = path.resolve().parts
    except Exception:  # noqa: BLE001
        parts = path.parts

    if len(parts) >= 3 and parts[0] == os.sep and parts[1] == "Volumes":
        return Path(os.sep, "Volumes", parts[2])
    return None


def _require_mounted(path: Path) -> None:
    mountpoint = _volume_mountpoint(path)
    if mountpoint is None:
        return
    if not mountpoint.exists() or not _is_mounted(mountpoint):
        raise SystemExit(f"Volume not mounted: {mountpoint}")


def _is_hidden_rel(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _iter_audio_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if _is_hidden_rel(rel):
            continue
        if path.suffix.lower() not in AUDIO_EXTS:
            continue
        yield path


def _files_identical(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    bufsize = 1024 * 1024
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca = fa.read(bufsize)
            cb = fb.read(bufsize)
            if ca != cb:
                return False
            if not ca:
                return True


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for idx in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{idx}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find unique path for: {path}")


def _batched_update_asset_file_paths(db_path: Path, updates: list[tuple[str, str]]) -> int:
    if not updates:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        total_updated = 0
        for start in range(0, len(updates), 1000):
            batch = updates[start : start + 1000]
            before = conn.total_changes
            conn.execute("BEGIN")
            conn.executemany(
                "UPDATE asset_file SET file_path = ? WHERE file_path = ?",
                [(new, old) for (old, new) in batch],
            )
            conn.commit()
            updated = conn.total_changes - before
            total_updated += updated
            print(f"DB batch updated rows: {updated} (batch size: {len(batch)})")
        return total_updated
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Move audio files from mp3_leftorvers to MP3_LIBRARY_CLEAN, update asset_file paths, and remove empty dirs."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite DB path (e.g. /Users/.../music_v3.db)",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("/Volumes/MUSIC/mp3_leftorvers"),
        help="Source root (default: /Volumes/MUSIC/mp3_leftorvers)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("/Volumes/MUSIC/MP3_LIBRARY_CLEAN"),
        help="Destination root (default: /Volumes/MUSIC/MP3_LIBRARY_CLEAN)",
    )
    parser.add_argument(
        "--conflict-root",
        type=Path,
        default=Path("/Volumes/MUSIC/_work/cleanup_mp3_consolidate_conflicts"),
        help="Conflict root (default: /Volumes/MUSIC/_work/cleanup_mp3_consolidate_conflicts)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not move or update DB.")
    parser.add_argument("--execute", action="store_true", help="Actually move files, update DB, and remove empty dirs.")
    args = parser.parse_args()

    if bool(args.dry_run) == bool(args.execute):
        raise SystemExit("Provide exactly one of --dry-run or --execute.")

    source_root = args.source.expanduser().resolve()
    dest_root = args.dest.expanduser().resolve()
    conflict_root = args.conflict_root.expanduser().resolve()
    db_path = args.db.expanduser().resolve() if args.db is not None else None

    _require_mounted(source_root)
    _require_mounted(dest_root)
    _require_mounted(conflict_root)

    if not source_root.is_dir():
        raise SystemExit(f"Source not found or not a directory: {source_root}")
    if dest_root.exists() and not dest_root.is_dir():
        raise SystemExit(f"Destination exists but is not a directory: {dest_root}")
    if args.execute and not dest_root.exists():
        dest_root.mkdir(parents=True, exist_ok=True)
    if args.execute:
        if db_path is None:
            raise SystemExit("--db is required with --execute.")
        if not db_path.is_file():
            raise SystemExit(f"DB not found: {db_path}")

    summary = Summary()
    pending_db_updates: list[tuple[str, str]] = []

    for src in _iter_audio_files(source_root):
        rel = src.relative_to(source_root)
        dest = (dest_root / rel)

        summary.total_audio_files += 1
        ext = src.suffix.lower()
        if ext == ".mp3":
            summary.format_mp3 += 1
        elif ext == ".m4a":
            summary.format_m4a += 1
        else:
            summary.format_other += 1

        if dest.exists():
            summary.conflicts_dest_exists += 1

        if args.dry_run:
            continue

        try:
            src_resolved = src.resolve()
            dest_resolved = dest.resolve() if dest.exists() else dest

            if dest.exists():
                if _files_identical(src, dest):
                    summary.files_skipped_identical += 1
                    continue

                conflict_target = conflict_root / rel
                conflict_target.parent.mkdir(parents=True, exist_ok=True)
                conflict_target = _unique_path(conflict_target)
                shutil.move(str(src), str(conflict_target))
                summary.files_moved_to_conflicts += 1
                pending_db_updates.append((str(src_resolved), str(conflict_target.resolve())))
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.rename(str(src), str(dest))
                except OSError:
                    shutil.move(str(src), str(dest))
                summary.files_moved += 1
                pending_db_updates.append((str(src_resolved), str(dest_resolved.resolve())))
        except Exception as exc:  # noqa: BLE001
            summary.failed += 1
            print(f"FAILED: {src} ({exc})")
            continue

        if len(pending_db_updates) >= 1000:
            assert db_path is not None
            summary.db_rows_updated += _batched_update_asset_file_paths(db_path, pending_db_updates)
            pending_db_updates.clear()

    if args.execute and pending_db_updates:
        assert db_path is not None
        summary.db_rows_updated += _batched_update_asset_file_paths(db_path, pending_db_updates)
        pending_db_updates.clear()

    if args.execute:
        for dirpath, dirnames, filenames in os.walk(str(source_root), topdown=False):
            if dirnames or filenames:
                continue
            Path(dirpath).rmdir()
            summary.dirs_removed += 1
        if source_root.exists():
            try:
                source_root.rmdir()
                summary.dirs_removed += 1
            except OSError:
                pass

    if args.dry_run:
        print("DRY RUN summary:")
        print(f"  Total audio files: {summary.total_audio_files}")
        print(f"  Conflicts (dest exists): {summary.conflicts_dest_exists}")
        print(f"  Format breakdown: mp3={summary.format_mp3} m4a={summary.format_m4a} other={summary.format_other}")
        return 0

    print("FINAL summary:")
    print(f"  Files moved: {summary.files_moved}")
    print(f"  Files skipped (identical at dest): {summary.files_skipped_identical}")
    print(f"  Files in conflict dir: {summary.files_moved_to_conflicts}")
    print(f"  DB rows updated: {summary.db_rows_updated}")
    print(f"  Dirs removed: {summary.dirs_removed}")
    print(f"  Failed: {summary.failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
