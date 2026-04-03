#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from mutagen import File as MutagenFile


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}
CHUNK_SIZE = 1024 * 1024


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audit a pool for invalid audio and exact duplicates, optionally "
            "deduping by replacing duplicate files with hardlinks or deleting "
            "duplicate paths."
        )
    )
    parser.add_argument("root", help="Pool root to audit")
    parser.add_argument(
        "--manifest-dir",
        help="Directory for audit manifests",
        default=str(Path.cwd()),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Replace exact duplicate files with hardlinks to a canonical copy",
    )
    parser.add_argument(
        "--delete-duplicates",
        action="store_true",
        help="Delete duplicate paths and keep only one canonical path per exact duplicate group",
    )
    return parser.parse_args()


def is_audio_file(path):
    return path.suffix.lower() in AUDIO_EXTENSIONS and not path.name.startswith(".")


def iter_audio_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        current_root = Path(dirpath)
        for filename in filenames:
            path = current_root / filename
            if is_audio_file(path):
                yield path


def file_digest(path):
    digest = hashlib.blake2b(digest_size=20)
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_audio(path):
    try:
        audio = MutagenFile(path)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if audio is None:
        return False, "mutagen returned None"

    return True, ""


def choose_keeper(paths):
    return sorted(paths, key=lambda path: (len(str(path)), str(path)))[0]


def hardlink_replace(source_path, keeper_path):
    temp_path = source_path.with_name(f".{source_path.name}.hardlink_tmp")
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    os.link(keeper_path, temp_path)
    os.replace(temp_path, source_path)


def prune_empty_parent_dirs(path, stop_root):
    current = path.parent
    while current != stop_root and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def main():
    args = parse_args()
    if args.apply and args.delete_duplicates:
        raise SystemExit("Use only one of --apply or --delete-duplicates")

    root = Path(args.root).expanduser()
    manifest_dir = Path(args.manifest_dir).expanduser()
    invalid_manifest_path = manifest_dir / "pool_invalid_files.jsonl"
    duplicate_manifest_path = manifest_dir / "pool_duplicates.jsonl"

    size_index = defaultdict(list)
    stats = Counter()
    invalid_rows = []
    duplicate_rows = []

    for path in iter_audio_files(root):
        stats["files_scanned"] += 1

        try:
            stat_result = path.stat()
        except OSError as exc:
            stats["stat_errors"] += 1
            invalid_rows.append(
                {
                    "path": str(path),
                    "reason": f"{type(exc).__name__}: {exc}",
                    "size": None,
                }
            )
            continue

        size = stat_result.st_size
        stats["bytes_scanned"] += size

        if size == 0:
            stats["zero_byte_files"] += 1
            invalid_rows.append(
                {
                    "path": str(path),
                    "reason": "zero-byte file",
                    "size": size,
                }
            )
            continue

        is_valid, reason = validate_audio(path)
        if not is_valid:
            stats["invalid_audio_files"] += 1
            invalid_rows.append(
                {
                    "path": str(path),
                    "reason": reason,
                    "size": size,
                }
            )

        size_index[size].append(path)

    hash_cache = {}

    for size, paths in size_index.items():
        if len(paths) < 2:
            continue

        by_hash = defaultdict(list)
        for path in paths:
            key = str(path)
            digest = hash_cache.get(key)
            if digest is None:
                try:
                    digest = file_digest(path)
                except OSError as exc:
                    stats["hash_errors"] += 1
                    invalid_rows.append(
                        {
                            "path": str(path),
                            "reason": f"{type(exc).__name__}: {exc}",
                            "size": size,
                        }
                    )
                    continue
                hash_cache[key] = digest
            by_hash[digest].append(path)

        for digest, dup_paths in by_hash.items():
            if len(dup_paths) < 2:
                continue

            stats["duplicate_groups"] += 1
            stats["duplicate_paths"] += len(dup_paths)

            keeper = choose_keeper(dup_paths)
            inode_groups = defaultdict(list)
            for path in dup_paths:
                stat_result = path.stat()
                inode_groups[(stat_result.st_dev, stat_result.st_ino)].append(path)

            distinct_copies = len(inode_groups)
            reclaimable_copies = max(0, distinct_copies - 1)
            stats["duplicate_bytes_total"] += size * (len(dup_paths) - 1)
            stats["reclaimable_bytes"] += size * reclaimable_copies

            for path in sorted(dup_paths):
                row = {
                    "hash": digest,
                    "size": size,
                    "keeper": str(keeper),
                    "path": str(path),
                    "already_hardlinked": path.stat().st_ino == keeper.stat().st_ino,
                    "action": "keep" if path == keeper else (
                        "delete" if args.delete_duplicates else "hardlink"
                    ),
                }

                if path == keeper:
                    row["applied"] = False
                elif args.apply and path.stat().st_ino != keeper.stat().st_ino:
                    hardlink_replace(path, keeper)
                    row["applied"] = True
                    stats["files_hardlinked"] += 1
                elif args.delete_duplicates:
                    path.unlink()
                    prune_empty_parent_dirs(path, root)
                    row["applied"] = True
                    stats["files_deleted"] += 1
                else:
                    row["applied"] = False

                duplicate_rows.append(row)

    manifest_dir.mkdir(parents=True, exist_ok=True)
    with invalid_manifest_path.open("w", encoding="utf-8") as handle:
        for row in invalid_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    with duplicate_manifest_path.open("w", encoding="utf-8") as handle:
        for row in duplicate_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    print("Summary")
    print(f"- Root: {root}")
    print(f"- Files scanned: {stats['files_scanned']}")
    print(f"- Bytes scanned: {stats['bytes_scanned']}")
    print(f"- Zero-byte files: {stats['zero_byte_files']}")
    print(f"- Invalid audio files: {stats['invalid_audio_files']}")
    print(f"- Stat errors: {stats['stat_errors']}")
    print(f"- Hash errors: {stats['hash_errors']}")
    print(f"- Duplicate groups: {stats['duplicate_groups']}")
    print(f"- Duplicate paths: {stats['duplicate_paths']}")
    print(f"- Duplicate bytes total: {stats['duplicate_bytes_total']}")
    print(f"- Reclaimable bytes: {stats['reclaimable_bytes']}")
    if args.apply:
        print(f"- Files hardlinked: {stats['files_hardlinked']}")
        print("- Mode: apply")
    elif args.delete_duplicates:
        print(f"- Files deleted: {stats['files_deleted']}")
        print("- Mode: delete-duplicates")
    else:
        print("- Mode: audit-only")
    print(f"- Invalid manifest: {invalid_manifest_path}")
    print(f"- Duplicate manifest: {duplicate_manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
