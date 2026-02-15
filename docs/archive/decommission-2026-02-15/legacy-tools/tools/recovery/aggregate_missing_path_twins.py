#!/usr/bin/env python3
"""Deterministic aggregation of missing-path checksum twins."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8192):
            h.update(chunk)
    return h.hexdigest()


def iter_matches(path: Path):
    """Yields rows from the matches CSV, validating headers."""
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"relative_path", "checksum", "match_prefix"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Missing columns in {path}: {', '.join(sorted(missing))}")
        yield from reader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matches",
        type=Path,
        default=BASE_DIR / "missing_paths_RECOVERY_TARGET_checksum_matches.csv",
        help="CSV exported from missing-path report (defaults to %(default)s)",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=BASE_DIR / "missing_paths_RECOVERY_TARGET_checksum_twin_summary.csv",
        help="Checksum twin summary CSV (optional, only hashed for verification)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BASE_DIR,
        help="Directory to write aggregated outputs (defaults to repo root)",
    )
    args = parser.parse_args()

    all_paths: Set[str] = set()
    paths_with_match: Set[str] = set()
    prefix_paths: dict[str, set[str]] = {}
    prefix_checksums: dict[str, set[str]] = {}
    prefix_rows: dict[str, int] = {}
    path_checksums: dict[str, set[str]] = {}
    path_prefixes: dict[str, set[str]] = {}
    path_match_paths: dict[str, set[str]] = {}
    path_checksum_prefix: dict[str, set[tuple[str | None, str]]] = {}
    dedup = set()

    for row in iter_matches(args.matches):
        rel = row["relative_path"]
        checksum = row.get("checksum") or ""
        prefix = row.get("match_prefix") or ""
        match_path = row.get("match_path") or ""

        # Dedup exact rows (including match_path) to avoid processing duplicates
        # but allow multiple twins for the same file/prefix.
        row_key = (rel, checksum, prefix, match_path)
        if row_key in dedup:
            continue
        dedup.add(row_key)

        all_paths.add(rel)
        if prefix:
            paths_with_match.add(rel)
            prefix_paths.setdefault(prefix, set()).add(rel)
            if checksum:
                prefix_checksums.setdefault(prefix, set()).add(checksum)
            prefix_rows[prefix] = prefix_rows.get(prefix, 0) + 1
            path_checksum_prefix.setdefault(rel, set()).add((checksum, prefix))
        if checksum:
            path_checksums.setdefault(rel, set()).add(checksum)
        if prefix:
            path_prefixes.setdefault(rel, set()).add(prefix)
        if match_path:
            path_match_paths.setdefault(rel, set()).add(match_path)
            paths_with_match.add(rel)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Prefix summary
    by_prefix = sorted(
        (
            (prefix, len(prefix_paths.get(prefix, set())), len(prefix_checksums.get(prefix, set())), prefix_rows.get(prefix, 0))
            for prefix in prefix_paths
        ),
        key=lambda item: (-item[1], item[0]),
    )

    with (output_dir / "missing_paths_checksum_twins_by_prefix.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["match_prefix", "missing_path_count", "unique_checksums", "total_match_rows"])
        for row in by_prefix:
            writer.writerow(row)

    # Per-path collapse
    with (output_dir / "missing_paths_checksum_twin_collapse.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "relative_path",
                "checksum",
                "twin_count",
                "prefix_count",
                "prefixes",
                "first_seen_prefix",
                "last_seen_prefix",
            ]
        )
        for rel in sorted(all_paths):
            checksums = sorted(path_checksums.get(rel, set()))
            checksum_value = ";".join(checksums) if checksums else ""

            prefixes = sorted(path_prefixes.get(rel, set()))
            prefix_count = len(prefixes)
            prefixes_value = ",".join(prefixes)
            first_prefix = prefixes[0] if prefixes else ""
            last_prefix = prefixes[-1] if prefixes else ""

            if rel in path_match_paths:
                twin_count = len(path_match_paths.get(rel, set()))
            else:
                twin_count = len(path_checksum_prefix.get(rel, set()))

            writer.writerow(
                [
                    rel,
                    checksum_value,
                    twin_count,
                    prefix_count,
                    prefixes_value,
                    first_prefix,
                    last_prefix,
                ]
            )

    # Orphan list
    orphan_paths = sorted(all_paths - paths_with_match)
    with (output_dir / "missing_paths_without_any_checksum_twin.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["relative_path"])
        for rel in orphan_paths:
            writer.writerow([rel])

    if args.summary.exists():
        summary_sha = sha256_file(args.summary)
        print(f"Verified summary SHA256: {summary_sha}")

    print("Aggregated twins written to:", output_dir)


if __name__ == "__main__":
    main()
