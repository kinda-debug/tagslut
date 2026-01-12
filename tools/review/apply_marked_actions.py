#!/usr/bin/env python3
"""
Apply KEEP/DROP actions from a marked CSV.

Default is dry-run (no file changes). Use --execute to perform actions.
Actions:
- KEEP: copy to --keep-dest preserving relative path from --relative-root (default "/")
- DROP: if --drop-dest is provided, move there preserving relative path; otherwise report only

CSV columns expected: group_id,path,library,zone,action,reason,confidence,conflict_label,duration_diff,bitrate_diff,sample_rate_diff,bit_depth_diff,integrity_state,flac_ok
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import TextIO


def rel_to(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.as_posix().lstrip("/"))


def process(
    marked_csv: Path,
    keep_dest: Path | None,
    drop_dest: Path | None,
    root: Path,
    execute: bool,
    skip_missing: bool,
    skip_existing: bool,
    progress_every: int,
    log_file: TextIO | None,
    progress_only: bool,
    resume_file: Path | None,
) -> None:
    def log(message: str, *, always: bool = False) -> None:
        if not progress_only or always:
            print(message)
        if log_file:
            log_file.write(message + "\n")
            log_file.flush()

    def load_resume() -> int:
        if not resume_file or not resume_file.exists():
            return 0
        try:
            state = json.loads(resume_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log(f"[RESUME] Could not read resume file: {resume_file}", always=True)
            return 0
        try:
            stat = marked_csv.stat()
        except OSError:
            return 0
        if state.get("marked") != str(marked_csv):
            log(f"[RESUME] Resume file does not match marked CSV: {resume_file}", always=True)
            return 0
        if state.get("mtime") != stat.st_mtime or state.get("size") != stat.st_size:
            log(f"[RESUME] Resume file is stale for {marked_csv}; ignoring.", always=True)
            return 0
        return int(state.get("row", 0))

    def save_resume(row_index: int, total_rows: int) -> None:
        if not resume_file:
            return
        try:
            stat = marked_csv.stat()
            state = {
                "marked": str(marked_csv),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "row": row_index,
                "total_rows": total_rows,
            }
            resume_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            log(f"[RESUME] Failed to write resume file: {resume_file}", always=True)

    with marked_csv.open() as f:
        # Count rows upfront for a simple countdown tracker.
        total_rows = max(sum(1 for _ in f) - 1, 0)  # subtract header
        f.seek(0)
        reader = csv.DictReader(f)
        keep_dest_prefix = keep_dest.as_posix().rstrip("/") + "/" if keep_dest else None
        keep_actions = 0
        drop_actions = 0
        resume_from = load_resume()
        if resume_from:
            log(f"[RESUME] Starting from row {resume_from + 1}/{total_rows}", always=True)
        log(
            "Start run: "
            f"marked={marked_csv} execute={execute} skip_missing={skip_missing} "
            f"skip_existing={skip_existing} progress_every={progress_every}"
            + (f" resume_file={resume_file}" if resume_file else ""),
            always=True,
        )
        try:
            for row_index, row in enumerate(reader, start=1):
                if resume_from and row_index <= resume_from:
                    continue
                path = Path(row["path"])
                action = row.get("action")
                rel = rel_to(path, root)
                if action == "KEEP":
                    if not keep_dest:
                        log(f"[SKIP KEEP] no keep_dest set for {path}")
                        continue
                    if keep_dest_prefix and path.as_posix().startswith(keep_dest_prefix):
                        log(f"[SKIP KEEP] source already in keep_dest: {path}")
                        continue
                    target = keep_dest / rel
                    if skip_existing and target.exists():
                        log(f"[SKIP KEEP] target already exists: {target}")
                        continue
                    if execute:
                        try:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(path, target)
                            log(f"[KEEP] copied {path} -> {target}")
                        except FileNotFoundError:
                            if skip_missing:
                                log(f"[MISSING KEEP] {path} (skipping)")
                                continue
                            raise
                    else:
                        log(f"[DRY KEEP] would copy {path} -> {target}")
                    keep_actions += 1
                elif action == "DROP":
                    if skip_existing and not path.exists():
                        log(f"[SKIP DROP] source missing: {path}")
                        continue
                    if drop_dest:
                        target = drop_dest / rel
                        if execute:
                            try:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.move(path, target)
                                log(f"[DROP] moved {path} -> {target}")
                            except FileNotFoundError:
                                if skip_missing:
                                    log(f"[MISSING DROP] {path} (skipping)")
                                    continue
                                raise
                        else:
                            log(f"[DRY DROP] would move {path} -> {target}")
                    else:
                        if execute:
                            try:
                                path.unlink(missing_ok=True)
                                log(f"[DROP] deleted {path}")
                            except FileNotFoundError:
                                if skip_missing:
                                    log(f"[MISSING DROP] {path} (skipping)")
                                    continue
                                raise
                        else:
                            log(f"[DRY DROP] would delete {path}")
                    drop_actions += 1
                if progress_every and row_index % progress_every == 0:
                    remaining = max(total_rows - row_index, 0)
                    log(
                        f"[PROGRESS] processed {row_index}/{total_rows} "
                        f"(KEEP {keep_actions}, DROP {drop_actions}, remaining {remaining})",
                        always=True,
                    )
                    save_resume(row_index, total_rows)
        except KeyboardInterrupt:
            log(
                f"\nInterrupted. Summary so far: KEEP {keep_actions}, DROP {drop_actions} (execute={execute})",
                always=True,
            )
            save_resume(row_index if "row_index" in locals() else resume_from, total_rows)
            return
        log(f"Summary: KEEP {keep_actions}, DROP {drop_actions} (execute={execute})", always=True)
        save_resume(total_rows, total_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply KEEP/DROP from marked CSV (dry-run by default).")
    parser.add_argument(
        "--marked",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_marked_suggestions.csv",
        help="CSV with action column (KEEP/DROP)",
    )
    parser.add_argument(
        "--keep-dest",
        help="Destination root for KEEP files (required if any KEEP rows will be applied)",
    )
    parser.add_argument(
        "--drop-dest",
        help="Optional destination for DROP files (if omitted, DROP will delete)",
    )
    parser.add_argument(
        "--relative-root",
        default="/",
        help="Root to compute relative paths for copying/moving (default '/')",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform actions; otherwise dry-run",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip missing source files instead of aborting",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip KEEP when target exists and DROP when source missing (default: True)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print a progress line every N processed rows (0 to disable)",
    )
    parser.add_argument(
        "--log-file",
        help="Append all output to this file",
    )
    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Disable log file output",
    )
    parser.add_argument(
        "--progress-only",
        action="store_true",
        help="Only print progress and summary to stdout (use log file for full details)",
    )
    parser.add_argument(
        "--resume-file",
        help="Path to resume state file (JSON). Defaults to <marked>.resume.json",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Disable resume state tracking",
    )
    args = parser.parse_args()

    log_file = None
    if not args.no_log_file:
        log_path = Path(args.log_file).expanduser() if args.log_file else Path(args.marked).expanduser().with_suffix(".log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")

    resume_path = None
    if not args.no_resume:
        resume_path = Path(args.resume_file).expanduser() if args.resume_file else Path(args.marked).expanduser().with_suffix(".resume.json")
    try:
        process(
            marked_csv=Path(args.marked).expanduser(),
            keep_dest=Path(args.keep_dest).expanduser() if args.keep_dest else None,
            drop_dest=Path(args.drop_dest).expanduser() if args.drop_dest else None,
            root=Path(args.relative_root),
            execute=args.execute,
            skip_missing=args.skip_missing,
            skip_existing=args.skip_existing,
            progress_every=max(args.progress_every, 0),
            log_file=log_file,
            progress_only=args.progress_only,
            resume_file=resume_path,
        )
    finally:
        if log_file:
            log_file.close()


if __name__ == "__main__":
    main()
