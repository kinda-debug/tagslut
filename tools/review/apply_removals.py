#!/usr/bin/env python3
"""
Apply quarantine plans and perform retention-based deletions.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.utils import env_paths
from dedupe.storage.schema import init_db
from dedupe.utils.db import open_db, resolve_db_path
from dedupe.utils.validators import PreFlightValidator
from dedupe.utils.plan import PlanRow, load_plan_rows
from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.safety_gates import SafetyGates
from dedupe.utils.file_operations import FileOperations


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
    ui: ConsoleUI,
    file_ops: FileOperations,
    skip_missing: bool,
    skip_existing: bool,
    progress_every: int,
    progress_every_seconds: float | None,
    progress_only: bool,
    manifest_path: Path,
    resume: bool,
    progress_log_path: Path,
) -> None:
    rows = load_plan_rows(plan_path)
    if not file_ops.dry_run:
        quarantine_root.mkdir(parents=True, exist_ok=True)

    processed_files = set()
    if resume and progress_log_path.exists():
        with progress_log_path.open("r", encoding="utf-8") as f:
            processed_files = {line.strip() for line in f}
        ui.print(f"Resuming operation. Found {len(processed_files)} already processed files.")

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_fields = [
        "plan_id", "tier", "original_path", "quarantine_path", "keeper_path",
        "sha256", "source_zone", "reason", "quarantined_at",
    ]
    
    failed_dir = quarantine_root / "_failed"
    if not file_ops.dry_run:
        failed_dir.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("w", newline="") as manifest_file, progress_log_path.open("a", encoding="utf-8") as progress_log_file:
        writer = csv.DictWriter(manifest_file, fieldnames=manifest_fields)
        write_manifest_header(writer)

        last_progress = time.time()
        quarantined, skipped, total = 0, 0, len(rows)
        ui.print(f"Start run: plan={plan_path} total={total} execute={not file_ops.dry_run} skip_missing={skip_missing} skip_existing={skip_existing}")

        for index, row in enumerate(rows, start=1):
            src = Path(row.path)
            if str(src) in processed_files:
                skipped += 1
                continue

            rel = rel_to(src, relative_root)
            target = quarantine_root / rel
            if skip_existing and target.exists():
                ui.print(f"[SKIP] target exists: {target}")
                skipped += 1
                continue
            if not src.exists():
                if skip_missing:
                    ui.warning(f"[MISSING] {src}")
                    skipped += 1
                    continue
                raise FileNotFoundError(src)

            quarantined_at = now_utc()
            if not file_ops.dry_run:
                progress_log_file.write(f"{str(src)}\n")
                progress_log_file.flush()
                
                if file_ops.safe_copy(src, target, verify_checksum=True):
                    with conn:
                        conn.execute(
                            "INSERT INTO file_quarantine (original_path, quarantine_path, sha256, keeper_path, source_zone, reason, tier, plan_id, quarantined_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (str(src), str(target), row.sha256, row.keeper_path, row.source_zone, row.reason, row.tier, row.plan_id, quarantined_at),
                        )
                        conn.execute("UPDATE files SET path = ?, zone = 'quarantine' WHERE path = ?", (str(target), str(src)))
                    ui.print(f"[QUARANTINE] {src} -> {target}")
                else:
                    ui.error(f"Failed to copy or verify {src} to {target}")
                    # Move corrupted file to failed directory
                    failed_target = failed_dir / rel
                    if file_ops.safe_move(target, failed_target, confirmation_phrase="move corrupted file"):
                        ui.print(f"Moved corrupted file to {failed_target}")
                    else:
                        ui.error(f"Could not move corrupted file at {target}")
                    skipped += 1
                    continue
            else:
                ui.print(f"[DRY QUARANTINE] {src} -> {target}")
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
        
        ui.print(f"Summary: QUARANTINE {quarantined}, SKIP {skipped} (execute={not file_ops.dry_run})")

def apply_deletions(
    conn,
    delete_after_days: int,
    ui: ConsoleUI,
    file_ops: FileOperations,
) -> None:
    ui.error("CRITICAL: Deletion phase is DISABLED. No files will be removed.")
    return


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
    parser.add_argument("--progress-only", action="store_true")
    parser.add_argument("--manifest", help="CSV manifest path")
    parser.add_argument("--delete-after-days", type=int, help="Delete quarantined files after N days")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted operation")
    args = parser.parse_args()

    ui = ConsoleUI(quiet=args.progress_only)
    gates = SafetyGates(ui)
    file_ops = FileOperations(ui, gates, dry_run=not args.execute)

    if args.delete_after_days is not None and args.plan:
        raise ValueError("Use either --plan (quarantine) or --delete-after-days (delete), not both.")
    if args.delete_after_days is None and not args.plan:
        raise ValueError("Provide --plan for quarantine or --delete-after-days for deletion.")

    if not args.delete_after_days:
        plan_path = Path(args.plan) if args.plan else env_paths.get_reports_dir() / "removal_plan.csv"
        quarantine_root = Path(args.quarantine_root) if args.quarantine_root else env_paths.get_quarantine_volume()
        validator = PreFlightValidator(quarantine_root, plan_path, args.db, args.execute)

        errors = []
        if not validator.validate():
            errors.extend(validator.get_errors())

        if errors:
            for error in errors:
                ui.error(error)
            sys.exit(1)

    if args.execute:
        prompt = "This will MOVE files to the quarantine location. This is a destructive operation."
        required_phrase = "I accept the risks and have verified my backups."
        if not gates.confirm_destructive_operation(prompt, required_phrase):
            ui.warning("User aborted operation.")
            sys.exit(0)

    resolution = resolve_db_path(args.db, purpose="write", allow_repo_db=False, source_label="cli")
    conn = open_db(resolution, row_factory=True)
    init_db(conn)

    if args.delete_after_days is not None:
        apply_deletions(conn, delete_after_days=args.delete_after_days, ui=ui, file_ops=file_ops)
    else:
        manifest = Path(args.manifest or env_paths.get_reports_dir() / f"quarantine_manifest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv")
        plan_path = Path(args.plan) if args.plan else env_paths.get_reports_dir() / "removal_plan.csv"
        quarantine_root = Path(args.quarantine_root) if args.quarantine_root else env_paths.get_quarantine_volume()
        if not quarantine_root:
             raise ValueError("Quarantine root not provided and VOLUME_QUARANTINE not set.")
        progress_log_path = env_paths.get_logs_dir() / "quarantine_progress.log"
        apply_quarantine(
            conn, plan_path=plan_path, quarantine_root=quarantine_root, relative_root=Path(args.relative_root),
            ui=ui, file_ops=file_ops, skip_missing=args.skip_missing, skip_existing=args.skip_existing,
            progress_every=args.progress_every, progress_every_seconds=args.progress_every_seconds,
            progress_only=args.progress_only, manifest_path=manifest,
            resume=args.resume, progress_log_path=progress_log_path
        )

    conn.close()

if __name__ == "__main__":
    main()