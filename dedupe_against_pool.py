#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}
CHUNK_SIZE = 1024 * 1024


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Find exact audio duplicates in old roots against a canonical POOL_LIBRARY, "
            "optionally moving duplicates to an archive and replacing APFS-side paths "
            "with symlinks."
        )
    )
    parser.add_argument("pool_root", help="Canonical POOL_LIBRARY root")
    parser.add_argument("archive_root", help="Archive root for moved duplicates")
    parser.add_argument("candidate_roots", nargs="+", help="Old roots to dedupe against the pool")
    parser.add_argument(
        "--manifest",
        help="Path to write the duplicate manifest JSONL",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move duplicates to the archive and replace APFS-side sources with symlinks",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file actions",
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


def index_pool(pool_root):
    by_size = defaultdict(list)
    for path in iter_audio_files(pool_root):
        try:
            size = path.stat().st_size
        except OSError:
            continue
        by_size[size].append(path)
    return by_size


def archive_destination(archive_root, candidate_root, source_path):
    relative = source_path.relative_to(candidate_root)
    root_label = candidate_root.name.rstrip() or "root"
    target = archive_root / root_label / relative
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem}__dup_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def can_symlink(path):
    return str(path).startswith("/Volumes/MUSIC/")


def verbose_print(enabled, message):
    if enabled:
        print(message)


def main():
    args = parse_args()

    pool_root = Path(args.pool_root).expanduser()
    archive_root = Path(args.archive_root).expanduser()
    candidate_roots = [Path(root).expanduser() for root in args.candidate_roots]
    manifest_path = (
        Path(args.manifest).expanduser()
        if args.manifest
        else Path.cwd() / "dedupe_against_pool_manifest.jsonl"
    )

    pool_index = index_pool(pool_root)
    pool_hash_cache = {}
    stats = Counter()
    manifest_rows = []

    for candidate_root in candidate_roots:
        if not candidate_root.exists():
            stats["missing_candidate_roots"] += 1
            continue

        for source_path in iter_audio_files(candidate_root):
            stats["candidate_files"] += 1
            try:
                source_size = source_path.stat().st_size
            except OSError:
                stats["candidate_errors"] += 1
                continue

            if source_size == 0:
                stats["zero_byte_skipped"] += 1
                continue

            pool_matches = pool_index.get(source_size, [])
            if not pool_matches:
                stats["unique_by_size"] += 1
                continue

            try:
                source_hash = file_digest(source_path)
            except OSError:
                stats["candidate_errors"] += 1
                continue

            match_path = None
            for pool_path in pool_matches:
                key = str(pool_path)
                pool_hash = pool_hash_cache.get(key)
                if pool_hash is None:
                    try:
                        pool_hash = file_digest(pool_path)
                    except OSError:
                        continue
                    pool_hash_cache[key] = pool_hash
                if pool_hash == source_hash:
                    match_path = pool_path
                    break

            if match_path is None:
                stats["unique_by_hash"] += 1
                continue

            archive_path = archive_destination(archive_root, candidate_root, source_path)
            symlink_path = str(match_path) if can_symlink(source_path) else None
            action = "move+symlink" if symlink_path else "move-only"

            manifest_rows.append(
                {
                    "action": action,
                    "candidate_root": str(candidate_root),
                    "source": str(source_path),
                    "pool_target": str(match_path),
                    "archive_target": str(archive_path),
                    "size": source_size,
                }
            )
            stats["exact_dupe_files"] += 1
            stats["exact_dupe_bytes"] += source_size

            if not args.apply:
                continue

            archive_path.parent.mkdir(parents=True, exist_ok=True)
            verbose_print(args.verbose, f"move {source_path} -> {archive_path}")
            shutil.move(str(source_path), str(archive_path))

            if symlink_path:
                verbose_print(args.verbose, f"symlink {source_path} -> {match_path}")
                source_path.symlink_to(match_path)
                stats["symlinks_created"] += 1
            else:
                stats["moved_without_symlink"] += 1

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        for row in manifest_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    print("Summary")
    print(f"- Pool root: {pool_root}")
    print(f"- Archive root: {archive_root}")
    print(f"- Candidate roots: {len(candidate_roots)}")
    print(f"- Candidate files scanned: {stats['candidate_files']}")
    print(f"- Exact duplicates: {stats['exact_dupe_files']}")
    print(f"- Exact duplicate bytes: {stats['exact_dupe_bytes']}")
    print(f"- Unique by size: {stats['unique_by_size']}")
    print(f"- Unique by hash: {stats['unique_by_hash']}")
    print(f"- Zero-byte skipped: {stats['zero_byte_skipped']}")
    print(f"- Candidate errors: {stats['candidate_errors']}")
    print(f"- Missing candidate roots: {stats['missing_candidate_roots']}")
    if args.apply:
        print(f"- Symlinks created: {stats['symlinks_created']}")
        print(f"- Moved without symlink: {stats['moved_without_symlink']}")
        print("- Mode: apply")
    else:
        print("- Mode: manifest-only")
    print(f"- Manifest: {manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
