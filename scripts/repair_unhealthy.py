#!/usr/bin/env python3
"""
Helper to locate and optionally repair 'unhealthy keeper' files.

Workflow:
- Read a newline-separated list of absolute paths (default: unhealthy_keepers.txt).
- For each path: check if it exists. If missing, search configured trash dirs for basename matches.
- Produce a JSON report with candidates and statuses (dry-run by default).
- Optionally call the existing `flac_repair.py` on found candidates with `--apply`.

This tool is safe by default (dry-run). Use `--apply` to run repairs and `--repairs-out` to
set the repair output directory. The script will not overwrite files unless `--overwrite` is
passed to the underlying repair command.
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
from pathlib import Path
from typing import Dict, List
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find and optionally repair unhealthy keeper files"
    )
    p.add_argument(
        "--list",
        "-l",
        dest="list_file",
        default="unhealthy_keepers.txt",
        help=(
            "Path to file containing unhealthy keeper paths (one per line)"
        ),
    )
    p.add_argument(
        "--trash-dirs",
        dest="trash_dirs",
        nargs="*",
        default=[
            "/Volumes/dotad/MUSIC/_TRASH_DUPES_*",
            "/Volumes/dotad/MUSIC/REPAIRED/_TRASH_HASH_DUPES_*",
        ],
        help=(
            "Glob patterns for trash directories to search for candidates"
        ),
    )
    p.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help=(
            "Print report and do not run repairs (default)"
        ),
    )
    p.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        help=(
            "Run repair on selected candidate files (calls flac_repair.py)"
        ),
    )
    p.add_argument(
        "--repairs-out",
        dest="repairs_out",
        default="/Volumes/dotad/MUSIC/REPAIRED/repairs_batch",
        help=(
            "Output directory for repaired files"
        ),
    )
    p.add_argument(
        "--report",
        dest="report",
        default="repair_unhealthy_report.json",
        help=(
            "Path to write JSON report"
        ),
    )
    p.add_argument(
        "--max-candidates",
        dest="max_candidates",
        type=int,
        default=20,
        help=(
            "Maximum candidate matches to record per missing path"
        ),
    )
    return p.parse_args()


def read_list(path: Path) -> List[str]:
    if not path.exists():
        print(f"List file not found: {path}")
        return []

    # Read entire file and normalize any literal "\\n" sequences that may have
    # been embedded into single-line entries (e.g. JSON fields that encoded
    # multiple paths as a single string with literal "\\n"). Replace those
    # with real newlines and then split into individual paths.
    content = path.read_text(encoding="utf-8")
    # Convert literal backslash+n into actual newlines
    content = content.replace("\\n", "\n")
    # Split into lines, strip and ignore empties
    raw_lines = [line.strip() for line in content.splitlines() if line.strip()]

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for line in raw_lines:
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def find_candidates(
    basename: str,
    trash_globs: List[str],
    max_candidates: int,
) -> List[str]:
    """Search configured trash directories for files containing *basename*.

    Returns up to `max_candidates` absolute paths (strings).
    """
    candidates: List[str] = []
    for pattern in trash_globs:
        # Use glob.glob which supports absolute patterns and shell-style globs
        try:
            roots = glob.glob(pattern)
        except Exception:
            roots = []
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            # rglob for basename substring (case-insensitive could be added)
            try:
                for p in root_path.rglob(f"*{basename}*"):
                    if p.is_file():
                        candidates.append(str(p))
                        if len(candidates) >= max_candidates:
                            return candidates
            except Exception:
                # ignore permission or filesystem errors for this root
                continue
    return candidates


def run_repair(candidate: str, repairs_out: str) -> Dict[str, object]:
    """Invoke flac_repair.py on candidate.

    Returns a small dict with status info.
    """
    cmd = [
        sys.executable,
        "flac_repair.py",
        "--file",
        candidate,
        "--output",
        repairs_out,
        "--capture-stderr",
    ]
    try:
        proc = subprocess.run(cmd, check=False)
        return {"exit_code": proc.returncode}
    except Exception as exc:
        return {"exit_code": None, "error": str(exc)}


def main() -> int:
    args = parse_args()
    list_file = Path(args.list_file)
    trash_globs = args.trash_dirs
    max_candidates = int(args.max_candidates)

    entries = read_list(list_file)
    report: Dict[str, Dict] = {}

    for orig in entries:
        rec: Dict = {"original": orig, "status": "missing", "candidates": []}
        p = Path(orig)
        if p.is_file():
            rec["status"] = "exists"
            rec["selected"] = str(p)
            report[orig] = rec
            continue

        # missing: search trash dirs by basename
        basename = p.name
        candidates = find_candidates(basename, trash_globs, max_candidates)
        if candidates:
            rec["status"] = "found_in_trash"
            rec["candidates"] = candidates
            # Heuristic: pick the largest candidate as selected
            try:
                def _size(path_str: str) -> int:
                    return Path(path_str).stat().st_size

                selected = max(candidates, key=_size)
                rec["selected"] = selected
            except Exception:
                rec["selected"] = candidates[0]
        else:
            rec["status"] = "not_found"

        # Optionally run repair on the selected candidate
        if args.apply and rec.get("selected"):
            res = run_repair(rec["selected"], args.repairs_out)
            rec["repair"] = res

        report[orig] = rec

    # Write JSON report
    try:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        print(f"Wrote report: {args.report}")
    except Exception as exc:
        print(f"Failed to write report: {exc}")
        return 2

    # Print a short summary
    total = len(report)
    found = sum(1 for v in report.values() if v.get("status") != "not_found")
    missing = total - found
    print(
        "Processed {} entries: {} found or existing, {} missing".format(
            total, found, missing
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
