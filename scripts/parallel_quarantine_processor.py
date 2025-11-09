#!/usr/bin/env python3
"""
Parallel subdirectory processor for Quarantine.

Discovers top-level subdirs in the Quarantine root, runs duration probes in
parallel (N at a time), merges results, ranks top mismatches, and
fast-inspects them.

Usage:
    python3 scripts/parallel_quarantine_processor.py \\
        --root /Volumes/dotad/Quarantine \\
        --output-dir /tmp/quarantine_parallel \\
        --parallel 4 \\
        --top 50 \\
        --verbose
"""

import argparse
import csv
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def discover_subdirs(root):
    """List immediate subdirectories of root."""
    subdirs = []
    try:
        for entry in os.listdir(root):
            full_path = os.path.join(root, entry)
            if os.path.isdir(full_path):
                subdirs.append((entry, full_path))
    except Exception as e:
        print(f"ERROR discovering subdirs in {root}: {e}", file=sys.stderr)
    return sorted(subdirs)


def run_duration_probe(subdir_name, subdir_path, output_csv, verbose=False):
    """
    Run quarantine duration probe on a single subdirectory.
    Returns (subdir_name, success, output_csv, row_count, error_msg)
    """
    try:
        cmd = [
            sys.executable,
            "-m",
            "dedupe.cli",
            "quarantine",
            "duration",
            subdir_path,
            "--output",
            output_csv,
        ]
        if verbose:
            cmd.append("--verbose")

        print(f"[{subdir_name}] Starting duration probe...", file=sys.stderr)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout per subdir
        )

        if result.returncode != 0:
            error_msg = (
                f"Command failed (exit {result.returncode}): "
                f"{result.stderr}"
            )
            print(f"[{subdir_name}] ERROR: {error_msg}", file=sys.stderr)
            return (subdir_name, False, output_csv, 0, error_msg)

        # Count rows in output CSV (excluding header)
        row_count = 0
        if os.path.exists(output_csv):
            with open(output_csv) as f:
                row_count = sum(1 for _ in f) - 1  # subtract header
        print(
            f"[{subdir_name}] SUCCESS: {row_count} rows written to "
            f"{output_csv}",
            file=sys.stderr,
        )
        return (subdir_name, True, output_csv, row_count, None)

    except subprocess.TimeoutExpired:
        error_msg = "Timeout (1 hour exceeded)"
        print(f"[{subdir_name}] ERROR: {error_msg}", file=sys.stderr)
        return (subdir_name, False, output_csv, 0, error_msg)
    except Exception as e:
        error_msg = str(e)
        print(f"[{subdir_name}] ERROR: {error_msg}", file=sys.stderr)
        return (subdir_name, False, output_csv, 0, error_msg)


def merge_csvs(csv_files: list, output_file: str) -> int:
    """Merge multiple CSVs (all with same header) into one."""
    if not csv_files:
        print("No CSVs to merge.", file=sys.stderr)
        return 0

    header = None
    total_rows = 0
    writer = None

    with open(output_file, "w", newline="") as out_f:
        for csv_file in csv_files:
            if not os.path.exists(csv_file):
                continue

            with open(csv_file) as in_f:
                reader = csv.DictReader(in_f)
                if header is None:
                    header = reader.fieldnames
                    if header is not None:
                        writer = csv.DictWriter(out_f, fieldnames=header)
                        writer.writeheader()

                if writer is not None:
                    for row in reader:
                        writer.writerow(row)
                        total_rows += 1

    msg = (
        f"Merged {len(csv_files)} CSVs into {output_file}: "
        f"{total_rows} rows"
    )
    print(msg, file=sys.stderr)
    return total_rows


def rank_duration_deltas(
    input_csv: str, output_csv: str, top_n: int
) -> bool:
    """Rank CSV by duration delta and write top N."""
    try:
        cmd = [
            sys.executable,
            "scripts/rank_duration_deltas.py",
            "--input",
            input_csv,
            "--output",
            output_csv,
            "--top",
            str(top_n),
        ]
        print(
            f"Running ranker: {' '.join(cmd)}", file=sys.stderr
        )
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            msg = (
                f"Ranker failed (exit {result.returncode}): "
                f"{result.stderr}"
            )
            print(msg, file=sys.stderr)
            return False

        print(f"Ranking complete: {output_csv}", file=sys.stderr)
        return True

    except Exception as e:
        print(f"Ranker error: {e}", file=sys.stderr)
        return False


def extract_top_paths(
    rank_csv: str, output_paths_file: str, top_n: int
) -> bool:
    """Extract top N paths from ranked CSV."""
    try:
        with open(rank_csv) as f:
            reader = csv.DictReader(f)
            paths = [
                row["path"] for i, row in enumerate(reader) if i < top_n
            ]

        with open(output_paths_file, "w") as f:
            for path in paths:
                f.write(f"{path}\n")

        msg = f"Extracted {len(paths)} top paths to {output_paths_file}"
        print(msg, file=sys.stderr)
        return True

    except Exception as e:
        print(f"Path extraction error: {e}", file=sys.stderr)
        return False


def fast_inspect_paths(paths_file: str, output_csv: str) -> bool:
    """Run fast inspection on paths."""
    try:
        cmd = [
            sys.executable,
            "scripts/fast_inspect_paths.py",
            "--paths",
            paths_file,
            "--output",
            output_csv,
        ]
        print(
            f"Running fast inspector: {' '.join(cmd)}", file=sys.stderr
        )
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )

        if result.returncode != 0:
            msg = (
                f"Inspector failed (exit {result.returncode}): "
                f"{result.stderr}"
            )
            print(msg, file=sys.stderr)
            return False

        print(f"Fast inspection complete: {output_csv}", file=sys.stderr)
        return True

    except Exception as e:
        print(f"Inspector error: {e}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parallel subdirectory processor for Quarantine directory."
    )
    parser.add_argument(
        "--root",
        default="/Volumes/dotad/Quarantine",
        help="Quarantine root directory.",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/quarantine_parallel",
        help="Output directory for CSVs and logs.",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Max parallel duration probes.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Number of top mismatches to inspect.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output.",
    )

    args = parser.parse_args()

    # Ensure output dir exists
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Quarantine Parallel Processor", file=sys.stderr)
    print(f"Root: {args.root}", file=sys.stderr)
    print(f"Output dir: {args.output_dir}", file=sys.stderr)
    print(f"Parallel jobs: {args.parallel}", file=sys.stderr)
    print(f"Top N to inspect: {args.top}", file=sys.stderr)
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
    print("", file=sys.stderr)

    # Discover subdirs
    subdirs = discover_subdirs(args.root)
    if not subdirs:
        print("ERROR: No subdirectories found.", file=sys.stderr)
        return 1

    print(f"Found {len(subdirs)} subdirectories:", file=sys.stderr)
    for name, path in subdirs:
        print(f"  {name}", file=sys.stderr)
    print("", file=sys.stderr)

    # Run parallel duration probes
    print(f"Launching {min(args.parallel, len(subdirs))} parallel probes...", file=sys.stderr)
    results = []
    per_subdir_csvs = {}

    with ThreadPoolExecutor(max_workers=args.parallel) as executor:
        futures = {}
        for subdir_name, subdir_path in subdirs:
            output_csv = os.path.join(
                args.output_dir, f"{subdir_name}_duration.csv"
            )
            future = executor.submit(
                run_duration_probe,
                subdir_name,
                subdir_path,
                output_csv,
                args.verbose,
            )
            futures[future] = (subdir_name, output_csv)

        for future in as_completed(futures):
            subdir_name, output_csv = futures[future]
            try:
                result = future.result()
                results.append(result)
                per_subdir_csvs[subdir_name] = output_csv
                print(
                    f"[{subdir_name}] Result: success={result[1]}, rows={result[3]}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(f"[{subdir_name}] Unhandled error: {e}", file=sys.stderr)

    print("", file=sys.stderr)

    # Summarize results
    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]

    print(f"Probe summary:", file=sys.stderr)
    print(f"  Successful: {len(successful)}", file=sys.stderr)
    print(f"  Failed: {len(failed)}", file=sys.stderr)
    for subdir_name, _, _, rows, _ in successful:
        print(f"    {subdir_name}: {rows} rows", file=sys.stderr)
    for subdir_name, _, _, _, error_msg in failed:
        print(f"    {subdir_name}: {error_msg}", file=sys.stderr)

    if not successful:
        print("ERROR: All probes failed.", file=sys.stderr)
        return 1

    # Merge successful CSVs
    successful_csvs = [
        per_subdir_csvs[r[0]] for r in successful if r[0] in per_subdir_csvs
    ]
    merged_csv = os.path.join(args.output_dir, "merged_duration.csv")
    total_rows = merge_csvs(successful_csvs, merged_csv)

    if total_rows == 0:
        print("ERROR: Merged CSV is empty.", file=sys.stderr)
        return 1

    print("", file=sys.stderr)

    # Rank top mismatches
    ranked_csv = os.path.join(args.output_dir, f"top_{args.top}_deltas.csv")
    if not rank_duration_deltas(merged_csv, ranked_csv, args.top):
        print("ERROR: Ranking failed.", file=sys.stderr)
        return 1

    # Extract and inspect top paths
    top_paths_file = os.path.join(args.output_dir, f"top_{args.top}_paths.txt")
    if not extract_top_paths(ranked_csv, top_paths_file, args.top):
        print("ERROR: Path extraction failed.", file=sys.stderr)
        return 1

    print("", file=sys.stderr)

    inspect_csv = os.path.join(args.output_dir, f"top_{args.top}_inspection.csv")
    if not fast_inspect_paths(top_paths_file, inspect_csv):
        print("WARNING: Fast inspection failed (continuing anyway).", file=sys.stderr)

    # Final summary
    print("", file=sys.stderr)
    print("PIPELINE COMPLETE", file=sys.stderr)
    print(f"End time: {time.strftime('%Y-%m-%d %H:%M:%S')}", file=sys.stderr)
    print("Output artifacts:", file=sys.stderr)
    subdir_pattern = os.path.join(args.output_dir, "*_duration.csv")
    print(f"  - Per-subdir CSVs: {subdir_pattern}", file=sys.stderr)
    print(f"  - Merged: {merged_csv}", file=sys.stderr)
    print(f"  - Ranked top {args.top}: {ranked_csv}", file=sys.stderr)
    print(f"  - Top {args.top} paths: {top_paths_file}", file=sys.stderr)
    print(f"  - Inspection: {inspect_csv}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Summary stats:", file=sys.stderr)
    print(f"  Total rows scanned: {total_rows}", file=sys.stderr)
    pct = f"{len(successful)}/{len(subdirs)}"
    print(f"  Successful subdirs: {pct}", file=sys.stderr)
    print(f"  Top {args.top} to inspect: {top_paths_file}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
