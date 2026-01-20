#!/usr/bin/env python3
"""
Apply quarantine plans and perform retention-based deletions.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.utils import env_paths
from dedupe.storage.schema import init_db
from dedupe.utils.db import open_db, resolve_db_path
from dedupe.utils.validators import PreFlightValidator
from dedupe.utils.plan import PlanRow, load_plan_rows

def validate_source_files(plan_path: Path) -> list[str]:
    errors = []
    rows = load_plan_rows(plan_path)
    if not rows:
        errors.append("No 'QUARANTINE' actions found in the plan.")
        return errors
        
    missing_count = 0
    for row in rows[:20]:  # Check first 20 rows
        if not Path(row.path).exists():
            missing_count += 1
    
    if missing_count > 5:  # If more than 5 of the first 20 are missing, something is wrong
        errors.append(f"{missing_count} of the first 20 source files in the plan are missing.")
    return errors

class OperationLog:
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_path.open("a", encoding="utf-8")

    def log(self, status: str, message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        self._log_file.write(f"[{timestamp}] [{status}] {message}\n")
        self._log_file.flush()

    def close(self) -> None:
        self._log_file.close()

def get_sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def verify_copy(src: Path, target: Path, expected_sha256: str | None) -> None:
    if not target.exists():
        raise IOError("Target file does not exist after copy.")
    if target.stat().st_size != src.stat().st_size:
        raise IOError("Target file size does not match source.")
    if expected_sha256:
        target_sha256 = get_sha256(target)
        if target_sha256 != expected_sha256:
            raise IOError(f"Target checksum mismatch. Expected {expected_sha256}, got {target_sha256}")

def rel_to(path: Path, root: Path) -> Path:
    path_str = path.as_posix()
    if len(path.parts) > 3 and path.parts[1] == "Volumes":
        return Path(*path.parts[3:])
    try:
        return path.relative_to(root)
    except ValueError:
        pass
    return Path(path_str.lstrip("/"))

def write_manifest_header(writer: csv.DictWriter) -> None:
    writer.writeheader()

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()



def apply_quarantine(
    conn,
    plan_path: Path,
    quarantine_root: Path,
    relative_root: Path,
    execute: bool,
    skip_missing: bool,
    skip_existing: bool,
    progress_every: int,
    progress_every_seconds: float | None,
    operation_log: OperationLog,
    progress_only: bool,
    manifest_path: Path,
    resume: bool,
    progress_log_path: Path,
) -> None:
    rows = load_plan_rows(plan_path)
    if execute:
        quarantine_root.mkdir(parents=True, exist_ok=True)

    processed_files = set()
    if resume and progress_log_path.exists():
        with progress_log_path.open("r", encoding="utf-8") as f:
            processed_files = {line.strip() for line in f}
        operation_log.log("INFO", f"Resuming operation. Found {len(processed_files)} already processed files.")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_fields = [
        "plan_id", "tier", "original_path", "quarantine_path", "keeper_path",
        "sha256", "source_zone", "reason", "quarantined_at",
    ]
    
    failed_dir = quarantine_root / "_failed"
    if execute:
        failed_dir.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("w", newline="") as manifest_file, progress_log_path.open("a", encoding="utf-8") as progress_log_file:
        writer = csv.DictWriter(manifest_file, fieldnames=manifest_fields)
        write_manifest_header(writer)

        last_progress = time.time()
        quarantined, skipped, total = 0, 0, len(rows)
        operation_log.log("INFO", f"Start run: plan={plan_path} total={total} execute={execute} skip_missing={skip_missing} skip_existing={skip_existing}")

        for index, row in enumerate(rows, start=1):
            src = Path(row.path)
            if str(src) in processed_files:
                skipped += 1
                continue

            rel = rel_to(src, relative_root)
            target = quarantine_root / rel
            if skip_existing and target.exists():
                operation_log.log("INFO", f"[SKIP] target exists: {target}")
                skipped += 1
                continue
            if not src.exists():
                if skip_missing:
                    operation_log.log("INFO", f"[MISSING] {src}")
                    skipped += 1
                    continue
                raise FileNotFoundError(src)

            quarantined_at = now_utc()
            if execute:
                progress_log_file.write(f"{str(src)}\n")
                progress_log_file.flush()
                
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src, target)
                    verify_copy(src, target, row.sha256)
                except (IOError, shutil.SameFileError, Exception) as e:
                    operation_log.log("ERROR", f"Failed to copy or verify {src} to {target}: {e}")
                    # Move corrupted file to failed directory
                    try:
                        failed_target = failed_dir / rel
                        failed_target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(target), str(failed_target))
                        operation_log.log("INFO", f"Moved corrupted file to {failed_target}")
                    except Exception as move_e:
                        operation_log.log("CRITICAL", f"Could not move corrupted file at {target}: {move_e}")
                    skipped += 1
                    continue

                with conn:
                    conn.execute(
                        "INSERT INTO file_quarantine (original_path, quarantine_path, sha256, keeper_path, source_zone, reason, tier, plan_id, quarantined_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (str(src), str(target), row.sha256, row.keeper_path, row.source_zone, row.reason, row.tier, row.plan_id, quarantined_at),
                    )
                    conn.execute("UPDATE files SET path = ?, zone = 'quarantine' WHERE path = ?", (str(target), str(src)))
                operation_log.log("SUCCESS", f"[QUARANTINE] {src} -> {target}")
            else:
                operation_log.log("INFO", f"[DRY QUARANTINE] {src} -> {target}")
                quarantined_at = ""

            writer.writerow({
                "plan_id": row.plan_id, "tier": row.tier, "original_path": str(src),
                "quarantine_path": str(target), "keeper_path": row.keeper_path, "sha256": row.sha256,
                "source_zone": row.source_zone, "reason": row.reason, "quarantined_at": quarantined_at,
            })
            quarantined += 1

            if progress_every and index % progress_every == 0:
                print(f"[PROGRESS] processed {index}/{total} (quarantined {quarantined}, skipped {skipped}, remaining {max(total - index, 0)})")
            if progress_every_seconds and (time.time() - last_progress >= progress_every_seconds):
                print(f"[PROGRESS] processed {index}/{total} (quarantined {quarantined}, skipped {skipped}, remaining {max(total - index, 0)})")
                last_progress = time.time()
        
        operation_log.log("INFO", f"Summary: QUARANTINE {quarantined}, SKIP {skipped} (execute={execute})")

def apply_deletions(
    conn,
    delete_after_days: int,
    execute: bool,
    operation_log: OperationLog,
) -> None:
    operation_log.log("CRITICAL", "Deletion phase is DISABLED. No files will be removed.")
    print("CRITICAL: Deletion phase is DISABLED. No files will be removed.")
    return

def confirm_execution(prompt: str, required_phrase: str) -> bool:
    print(f"WARNING: {prompt}")
    print(f"To confirm, you must type the following phrase exactly: '{required_phrase}'")
    response = input("> ").strip()
    return response == required_phrase

def main() -> None:
    parser = argparse.ArgumentParser(description="Apply quarantine plans and retention deletions.")
    parser.add_argument("--db", help="Path to dedupe DB")
    parser.add_argument("--plan", help="Removal plan CSV")
    parser.add_argument("--quarantine-root", help="Destination for quarantined files")
    parser.add_argument("--relative-root", default="/", help="Root to compute relative paths")
    parser.add_argument("--execute", action="store_true", help="Perform filesystem changes")
    parser.add_argument("--skip-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--progress-every", type=int, default=500, help="Print progress every N files")
    parser.add_argument("--progress-every-seconds", type=float)
    parser.add_argument("--log-file", help="Append all output to this log file")
    parser.add_argument("--progress-only", action="store_true")
    parser.add_argument("--manifest", help="CSV manifest path")
    parser.add_argument("--delete-after-days", type=int, help="Delete quarantined files after N days")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted operation")
    args = parser.parse_args()

    if args.delete_after_days is not None and args.plan:
        raise ValueError("Use either --plan (quarantine) or --delete-after-days (delete), not both.")
    if args.delete_after_days is None and not args.plan:
        raise ValueError("Provide --plan for quarantine or --delete-after-days for deletion.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = Path(args.log_file or env_paths.get_logs_dir() / f"apply_removals_{timestamp}.log")
    operation_log = OperationLog(log_path)

    if not args.delete_after_days:
        plan_path = Path(args.plan) if args.plan else env_paths.get_reports_dir() / "removal_plan.csv"
        quarantine_root = Path(args.quarantine_root) if args.quarantine_root else env_paths.get_quarantine_volume()
        validator = PreFlightValidator(quarantine_root, plan_path, args.db, args.execute)
        
        errors = []
        if not validator.validate():
            errors.extend(validator.get_errors())
        
        if args.execute:
            errors.extend(validate_source_files(plan_path))

        if errors:
            for error in errors:
                operation_log.log("ERROR", error)
                print(f"ERROR: {error}")
            sys.exit(1)

    if args.execute:
        prompt = "This will MOVE files to the quarantine location. This is a destructive operation."
        required_phrase = "I accept the risks and have verified my backups."
        if not confirm_execution(prompt, required_phrase):
            operation_log.log("INFO", "User aborted operation.")
            print("Aborting.")
            sys.exit(0)

    resolution = resolve_db_path(args.db, purpose="write", allow_repo_db=False, source_label="cli")
    conn = open_db(resolution, row_factory=True)
    init_db(conn)

    if args.delete_after_days is not None:
        apply_deletions(conn, delete_after_days=args.delete_after_days, execute=args.execute, operation_log=operation_log)
    else:
        manifest = Path(args.manifest or env_paths.get_reports_dir() / f"quarantine_manifest_{timestamp}.csv")
        plan_path = Path(args.plan) if args.plan else env_paths.get_reports_dir() / "removal_plan.csv"
        quarantine_root = Path(args.quarantine_root) if args.quarantine_root else env_paths.get_quarantine_volume()
        if not quarantine_root:
             raise ValueError("Quarantine root not provided and VOLUME_QUARANTINE not set.")
        progress_log_path = env_paths.get_logs_dir() / "quarantine_progress.log"
        apply_quarantine(
            conn, plan_path=plan_path, quarantine_root=quarantine_root, relative_root=Path(args.relative_root),
            execute=args.execute, skip_missing=args.skip_missing, skip_existing=args.skip_existing,
            progress_every=args.progress_every, progress_every_seconds=args.progress_every_seconds,
            operation_log=operation_log, progress_only=args.progress_only, manifest_path=manifest,
            resume=args.resume, progress_log_path=progress_log_path
        )

    conn.close()
    operation_log.close()

if __name__ == "__main__":
    main()