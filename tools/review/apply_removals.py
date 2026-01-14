#!/usr/bin/env python3
"""
Apply quarantine plans and perform retention-based deletions.

Default mode is quarantine-only (dry-run unless --execute is set).
Deletion is a separate explicit phase via --delete-after-days.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TextIO

from dedupe.storage.schema import init_db
from dedupe.utils.db import open_db, resolve_db_path


@dataclass(frozen=True)
class PlanRow:
    plan_id: str
    tier: str
    action: str
    reason: str
    sha256: str
    path: str
    source_zone: str
    keeper_path: str


def rel_to(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.as_posix().lstrip("/"))


def write_manifest_header(writer: csv.DictWriter) -> None:
    writer.writeheader()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_message(message: str, *, log_file: TextIO | None, progress_only: bool, always: bool = False) -> None:
    if not progress_only or always:
        print(message)
    if log_file:
        log_file.write(message + "\n")
        log_file.flush()


def load_plan_rows(plan_path: Path) -> list[PlanRow]:
    rows: list[PlanRow] = []
    with plan_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = (row.get("action") or "").strip().upper()
            if action != "QUARANTINE":
                continue
            rows.append(
                PlanRow(
                    plan_id=row.get("plan_id", ""),
                    tier=row.get("tier", ""),
                    action=action,
                    reason=row.get("reason", ""),
                    sha256=row.get("sha256", ""),
                    path=row.get("path", ""),
                    source_zone=row.get("source_zone", ""),
                    keeper_path=row.get("keeper_path", ""),
                )
            )
    return rows


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
    log_file: TextIO | None,
    progress_only: bool,
    manifest_path: Path,
) -> None:
    rows = load_plan_rows(plan_path)
    if execute:
        quarantine_root.mkdir(parents=True, exist_ok=True)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_fields = [
        "plan_id",
        "tier",
        "original_path",
        "quarantine_path",
        "keeper_path",
        "sha256",
        "source_zone",
        "reason",
        "quarantined_at",
    ]
    with manifest_path.open("w", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=manifest_fields)
        write_manifest_header(writer)

        last_progress = time.time()
        quarantined = 0
        skipped = 0
        total = len(rows)
        log_message(
            f"Start run: plan={plan_path} total={total} execute={execute} skip_missing={skip_missing} "
            f"skip_existing={skip_existing}",
            log_file=log_file,
            progress_only=progress_only,
            always=True,
        )

        for index, row in enumerate(rows, start=1):
            src = Path(row.path)
            rel = rel_to(src, relative_root)
            target = quarantine_root / rel
            if skip_existing and target.exists():
                log_message(f"[SKIP] target exists: {target}", log_file=log_file, progress_only=progress_only)
                skipped += 1
                continue
            if not src.exists():
                if skip_missing:
                    log_message(f"[MISSING] {src}", log_file=log_file, progress_only=progress_only)
                    skipped += 1
                    continue
                raise FileNotFoundError(src)

            quarantined_at = now_utc()
            if execute:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(src, target)
                with conn:
                    conn.execute(
                        """
                        INSERT INTO file_quarantine (
                            original_path,
                            quarantine_path,
                            sha256,
                            keeper_path,
                            source_zone,
                            reason,
                            tier,
                            plan_id,
                            quarantined_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(src),
                            str(target),
                            row.sha256,
                            row.keeper_path,
                            row.source_zone,
                            row.reason,
                            row.tier,
                            row.plan_id,
                            quarantined_at,
                        ),
                    )
                    conn.execute(
                        "UPDATE files SET path = ?, zone = 'quarantine' WHERE path = ?",
                        (str(target), str(src)),
                    )
                log_message(f"[QUARANTINE] {src} -> {target}", log_file=log_file, progress_only=progress_only)
            else:
                log_message(f"[DRY QUARANTINE] {src} -> {target}", log_file=log_file, progress_only=progress_only)
                quarantined_at = ""

            writer.writerow(
                {
                    "plan_id": row.plan_id,
                    "tier": row.tier,
                    "original_path": str(src),
                    "quarantine_path": str(target),
                    "keeper_path": row.keeper_path,
                    "sha256": row.sha256,
                    "source_zone": row.source_zone,
                    "reason": row.reason,
                    "quarantined_at": quarantined_at,
                }
            )
            quarantined += 1

            if progress_every and index % progress_every == 0:
                remaining = max(total - index, 0)
                log_message(
                    f"[PROGRESS] processed {index}/{total} (quarantined {quarantined}, skipped {skipped}, remaining {remaining})",
                    log_file=log_file,
                    progress_only=progress_only,
                    always=True,
                )
            if progress_every_seconds:
                now_ts = time.time()
                if now_ts - last_progress >= progress_every_seconds:
                    remaining = max(total - index, 0)
                    log_message(
                        f"[PROGRESS] processed {index}/{total} (quarantined {quarantined}, skipped {skipped}, remaining {remaining})",
                        log_file=log_file,
                        progress_only=progress_only,
                        always=True,
                    )
                    last_progress = now_ts

        log_message(
            f"Summary: QUARANTINE {quarantined}, SKIP {skipped} (execute={execute})",
            log_file=log_file,
            progress_only=progress_only,
            always=True,
        )


def apply_deletions(
    conn,
    delete_after_days: int,
    execute: bool,
    progress_every: int,
    progress_every_seconds: float | None,
    log_file: TextIO | None,
    progress_only: bool,
    manifest_path: Path,
) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=delete_after_days)
    rows = conn.execute(
        """
        SELECT id, original_path, quarantine_path, sha256, keeper_path, quarantined_at
        FROM file_quarantine
        WHERE deleted_at IS NULL AND quarantined_at <= ?
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_fields = [
        "original_path",
        "quarantine_path",
        "keeper_path",
        "sha256",
        "quarantined_at",
        "deleted_at",
    ]
    with manifest_path.open("w", newline="") as manifest_file:
        writer = csv.DictWriter(manifest_file, fieldnames=manifest_fields)
        write_manifest_header(writer)

        last_progress = time.time()
        deleted = 0
        skipped = 0
        total = len(rows)
        log_message(
            f"Start delete phase: eligible={total} execute={execute} cutoff={cutoff.isoformat()}",
            log_file=log_file,
            progress_only=progress_only,
            always=True,
        )

        for index, row in enumerate(rows, start=1):
            quarantine_path = Path(row["quarantine_path"])
            keeper_path = row["keeper_path"]
            sha256 = row["sha256"]
            quarantined_at = row["quarantined_at"]
            if not quarantine_path.exists():
                log_message(f"[SKIP] missing quarantine file: {quarantine_path}", log_file=log_file, progress_only=progress_only)
                skipped += 1
                continue

            keeper = conn.execute(
                "SELECT sha256, integrity_state, flac_ok FROM files WHERE path = ?",
                (keeper_path,),
            ).fetchone()
            if not keeper:
                log_message(f"[SKIP] missing keeper: {keeper_path}", log_file=log_file, progress_only=progress_only)
                skipped += 1
                continue
            if keeper["sha256"] != sha256 or keeper["integrity_state"] != "valid" or keeper["flac_ok"] != 1:
                log_message(
                    f"[SKIP] keeper not valid: {keeper_path}",
                    log_file=log_file,
                    progress_only=progress_only,
                )
                skipped += 1
                continue

            deleted_at = now_utc()
            if execute:
                quarantine_path.unlink(missing_ok=True)
                with conn:
                    conn.execute(
                        "UPDATE file_quarantine SET deleted_at = ?, delete_reason = ? WHERE id = ?",
                        (deleted_at, "retention_window_elapsed", row["id"]),
                    )
                    conn.execute("DELETE FROM files WHERE path = ?", (str(quarantine_path),))
                log_message(f"[DELETE] {quarantine_path}", log_file=log_file, progress_only=progress_only)
            else:
                log_message(f"[DRY DELETE] {quarantine_path}", log_file=log_file, progress_only=progress_only)
                deleted_at = ""

            writer.writerow(
                {
                    "original_path": row["original_path"],
                    "quarantine_path": str(quarantine_path),
                    "keeper_path": keeper_path,
                    "sha256": sha256,
                    "quarantined_at": quarantined_at,
                    "deleted_at": deleted_at,
                }
            )
            deleted += 1

            if progress_every and index % progress_every == 0:
                remaining = max(total - index, 0)
                log_message(
                    f"[PROGRESS] processed {index}/{total} (deleted {deleted}, skipped {skipped}, remaining {remaining})",
                    log_file=log_file,
                    progress_only=progress_only,
                    always=True,
                )
            if progress_every_seconds:
                now_ts = time.time()
                if now_ts - last_progress >= progress_every_seconds:
                    remaining = max(total - index, 0)
                    log_message(
                        f"[PROGRESS] processed {index}/{total} (deleted {deleted}, skipped {skipped}, remaining {remaining})",
                        log_file=log_file,
                        progress_only=progress_only,
                        always=True,
                    )
                    last_progress = now_ts

        log_message(
            f"Summary: DELETE {deleted}, SKIP {skipped} (execute={execute})",
            log_file=log_file,
            progress_only=progress_only,
            always=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply quarantine plans and retention deletions.")
    parser.add_argument("--db", required=True, help="Path to dedupe DB")
    parser.add_argument(
        "--plan",
        help="Removal plan CSV from tools/review/plan_removals.py",
    )
    parser.add_argument(
        "--quarantine-root",
        default="/Volumes/COMMUNE/M/_quarantine",
        help="Destination root for quarantined files",
    )
    parser.add_argument(
        "--relative-root",
        default="/",
        help="Root to compute relative paths (default '/')",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform filesystem changes; otherwise dry-run",
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        help="Skip missing sources instead of aborting",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip when quarantine target already exists (default: True)",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print progress every N files",
    )
    parser.add_argument(
        "--progress-every-seconds",
        type=float,
        default=None,
        help="Print progress every N seconds (continuous countdown)",
    )
    parser.add_argument("--log-file", help="Append all output to this log file")
    parser.add_argument(
        "--progress-only",
        action="store_true",
        help="Only print progress and summary to stdout",
    )
    parser.add_argument(
        "--manifest",
        help="CSV manifest path (quarantine or deletion)",
    )
    parser.add_argument(
        "--delete-after-days",
        type=int,
        default=None,
        help="Explicit deletion phase: delete quarantined files after N days",
    )
    args = parser.parse_args()

    if args.delete_after_days is not None and args.plan:
        raise ValueError("Use either --plan (quarantine) or --delete-after-days (delete), not both.")
    if args.delete_after_days is None and not args.plan:
        raise ValueError("Provide --plan for quarantine or --delete-after-days for deletion.")

    resolution = resolve_db_path(
        args.db,
        purpose="write",
        allow_repo_db=False,
        source_label="cli",
    )
    conn = open_db(resolution, row_factory=True)
    init_db(conn)

    log_file = None
    if args.log_file:
        log_path = Path(args.log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a", encoding="utf-8")

    if args.delete_after_days is not None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest = Path(
            args.manifest
            or f"/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/quarantine_deletions_{timestamp}.csv"
        )
        apply_deletions(
            conn,
            delete_after_days=args.delete_after_days,
            execute=args.execute,
            progress_every=args.progress_every,
            progress_every_seconds=args.progress_every_seconds,
            log_file=log_file,
            progress_only=args.progress_only,
            manifest_path=manifest,
        )
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        manifest = Path(
            args.manifest
            or f"/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/quarantine_manifest_{timestamp}.csv"
        )
        apply_quarantine(
            conn,
            plan_path=Path(args.plan),
            quarantine_root=Path(args.quarantine_root),
            relative_root=Path(args.relative_root),
            execute=args.execute,
            skip_missing=args.skip_missing,
            skip_existing=args.skip_existing,
            progress_every=args.progress_every,
            progress_every_seconds=args.progress_every_seconds,
            log_file=log_file,
            progress_only=args.progress_only,
            manifest_path=manifest,
        )

    conn.close()


if __name__ == "__main__":
    main()
