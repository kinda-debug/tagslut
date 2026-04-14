#!/usr/bin/env python3

import argparse
import os
import shutil
import sys
from pathlib import Path


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aif", ".aiff", ".flac"}


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild a canonical POOL_LIBRARY from a Rekordbox backup audio tree and an "
            "optional secondary DJUSB export tree."
        )
    )
    parser.add_argument("dest_root", help="Destination root for the rebuilt POOL_LIBRARY")
    parser.add_argument(
        "--primary-source",
        default="/Volumes/RBX_USB/rekordbox_bak",
        help="Primary audio recovery source",
    )
    parser.add_argument(
        "--secondary-source",
        default="/Volumes/DJUSB/Contents",
        help="Secondary audio recovery source",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report actions without copying files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file actions",
    )
    return parser.parse_args()


def verbose_print(enabled, message):
    if enabled:
        print(message)


def validate_destination_root(dest_root):
    dest_root = dest_root.expanduser().resolve(strict=False)

    if len(dest_root.parts) >= 3 and dest_root.parts[1] == "Volumes":
        volume_root = Path("/") / dest_root.parts[1] / dest_root.parts[2]
        if not volume_root.exists() or not volume_root.is_dir() or not os.path.ismount(volume_root):
            raise SystemExit(
                f"Refusing to use destination under unmounted volume root: {volume_root}"
            )

    if dest_root.exists() and not dest_root.is_dir():
        raise SystemExit(f"Destination exists and is not a directory: {dest_root}")

    return dest_root


def validate_source(source_root, required):
    if source_root.exists() and source_root.is_dir():
        return True

    if required:
        raise SystemExit(f"Required source is missing: {source_root}")

    return False


def is_audio_file(path):
    return path.suffix.lower() in AUDIO_EXTENSIONS and path.name != ".DS_Store"


def iter_audio_files(source_root):
    def onerror(error):
        raise error

    for root, dirnames, filenames in os.walk(source_root, onerror=onerror):
        dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        current_root = Path(root)
        for filename in sorted(filenames):
            source_path = current_root / filename
            if filename.startswith(".") or not is_audio_file(source_path):
                yield False, source_path, None
                continue
            yield True, source_path, source_path.relative_to(source_root)


def conflict_path(dest_path, suffix_label):
    stem = dest_path.stem
    suffix = dest_path.suffix
    candidate = dest_path.with_name(f"{stem}{suffix_label}{suffix}")
    counter = 1
    while candidate.exists():
        candidate = dest_path.with_name(f"{stem}{suffix_label}_{counter}{suffix}")
        counter += 1
    return candidate


def ensure_parent(path, dry_run):
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)


def print_summary(dest_root, primary_source, secondary_source, secondary_available, stats):
    print("\nSummary")
    print(f"- Destination root: {dest_root}")
    print(f"- Primary source: {primary_source}")
    print(f"- Secondary source: {secondary_source}")
    print(f"- Secondary available: {'yes' if secondary_available else 'no'}")
    print(f"- Audio files scanned from primary: {stats['primary_scanned']}")
    print(f"- Audio files scanned from secondary: {stats['secondary_scanned']}")
    print(f"- Copied from primary: {stats['primary_copied']}")
    print(f"- Copied from secondary: {stats['secondary_copied']}")
    print(f"- Resume-skipped existing files: {stats['same_size_skipped']}")
    print(f"- Secondary duplicates skipped: {stats['secondary_duplicates_skipped']}")
    print(f"- Conflicts copied with suffix: {stats['conflicts_copied']}")
    print(f"- Non-audio files ignored: {stats['non_audio_skipped']}")
    print(f"- Source/copy errors: {len(stats['errors'])}")
    print(f"- Bytes copied: {stats['bytes_copied']}")
    print(f"- Mode: {'dry-run' if stats['dry_run'] else 'write'}")
    if stats["errors"]:
        print("\nErrors (first 20)")
        for error in stats["errors"][:20]:
            print(f"- {error}")


def main():
    args = parse_args()

    dest_root = validate_destination_root(Path(args.dest_root))
    primary_source = Path(args.primary_source).expanduser()
    secondary_source = Path(args.secondary_source).expanduser()

    validate_source(primary_source, required=True)
    secondary_available = validate_source(secondary_source, required=False)

    stats = {
        "primary_scanned": 0,
        "secondary_scanned": 0,
        "primary_copied": 0,
        "secondary_copied": 0,
        "same_size_skipped": 0,
        "secondary_duplicates_skipped": 0,
        "conflicts_copied": 0,
        "non_audio_skipped": 0,
        "bytes_copied": 0,
        "dry_run": args.dry_run,
        "errors": [],
    }

    if not args.dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)

    def process_source(source_root, label):
        scanned_key = f"{label}_scanned"
        copied_key = f"{label}_copied"

        try:
            file_iter = iter_audio_files(source_root)
            for is_audio, source_path, relative_path in file_iter:
                if not is_audio:
                    stats["non_audio_skipped"] += 1
                    continue

                try:
                    source_size = source_path.stat().st_size
                except OSError as error:
                    stats["errors"].append(f"{source_path}: {error}")
                    continue

                stats[scanned_key] += 1
                dest_path = dest_root / relative_path

                if dest_path.exists():
                    try:
                        dest_size = dest_path.stat().st_size
                    except OSError as error:
                        stats["errors"].append(f"{dest_path}: {error}")
                        continue

                    if source_size == dest_size:
                        stats["same_size_skipped"] += 1
                        if label == "secondary":
                            stats["secondary_duplicates_skipped"] += 1
                        verbose_print(
                            args.verbose,
                            f"skip existing: {source_path} -> {dest_path}",
                        )
                        continue

                    suffix_label = "__conflict" if label == "secondary" else "__conflict_primary"
                    dest_path = conflict_path(dest_path, suffix_label)
                    stats["conflicts_copied"] += 1
                    verbose_print(
                        args.verbose,
                        f"conflict copy: {source_path} -> {dest_path}",
                    )
                else:
                    verbose_print(
                        args.verbose,
                        f"copy: {source_path} -> {dest_path}",
                    )

                ensure_parent(dest_path, args.dry_run)
                if not args.dry_run:
                    try:
                        shutil.copy2(source_path, dest_path)
                    except OSError as error:
                        stats["errors"].append(f"{source_path} -> {dest_path}: {error}")
                        continue

                stats[copied_key] += 1
                stats["bytes_copied"] += source_size
        except OSError as error:
            stats["errors"].append(f"{source_root}: {error}")

    process_source(primary_source, "primary")

    if secondary_available:
        process_source(secondary_source, "secondary")
    else:
        print(f"Warning: secondary source is not mounted, skipping: {secondary_source}")

    print_summary(dest_root, primary_source, secondary_source, secondary_available, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
