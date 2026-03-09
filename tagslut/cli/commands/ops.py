from __future__ import annotations

import csv
import json
import sqlite3
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

from tagslut.exec.canonical_writeback import iter_flacs_from_m3u, iter_flacs_from_root, write_canonical_tags
from tagslut.cli.runtime import PROJECT_ROOT
from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

_DOCTOR_COUNT_KEYS = (
    "asset_file_total",
    "asset_link_total",
    "track_identity_total",
    "integrity_done",
    "sha256_done",
    "enriched_done",
)
_DEFAULT_RECEIPT_DIR = PROJECT_ROOT / "plans" / "receipts"
_DEFAULT_PLAN_ARCHIVE_DIR = PROJECT_ROOT / "plans" / "archive"


@dataclass(frozen=True)
class DoctorRunResult:
    exit_code: int
    stdout: str
    stderr: str
    counts: dict[str, int]


@dataclass(frozen=True)
class ExecutorRunResult:
    exit_code: int
    stdout: str
    stderr: str
    receipts: list[object] | None
    dry_run_supported: bool


@dataclass(frozen=True)
class PlanSummary:
    plan_csv_path: Path
    executor_plan_path: Path
    temp_executor_plan_path: Path | None
    row_count: int
    move_count: int
    copy_count: int
    delete_count: int
    sample_rows: list[dict[str, str]]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _tail_lines(value: str, limit: int = 200) -> str:
    lines = value.splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


def _parse_doctor_counts(stdout: str, stderr: str) -> dict[str, int]:
    merged = "\n".join(part for part in (stdout, stderr) if part)
    counts = {key: 0 for key in _DOCTOR_COUNT_KEYS}
    for line in merged.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parsed_key = key.strip()
        if parsed_key not in counts:
            continue
        try:
            counts[parsed_key] = int(raw_value.strip())
        except ValueError:
            continue
    return counts


def _run_doctor(db_path: Path, *, strict: bool) -> DoctorRunResult:
    script = PROJECT_ROOT / "scripts" / "db" / "doctor_v3.py"
    cmd = [sys.executable, str(script), "--db", str(db_path)]
    if strict:
        cmd.append("--strict")
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return DoctorRunResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        counts=_parse_doctor_counts(proc.stdout, proc.stderr),
    )


def _normalize_mode(value: str) -> str:
    return value.strip().lower()


def _classify_mode(mode: str) -> str | None:
    normalized = _normalize_mode(mode)
    if normalized in {"move", "mv", "rename"}:
        return "move"
    if normalized in {"copy", "cp"}:
        return "copy"
    if normalized in {"delete", "del", "rm", "remove"}:
        return "delete"
    return None


def _validate_and_summarize_plan(plan_csv: Path) -> PlanSummary:
    plan_path = plan_csv.expanduser().resolve()
    if not plan_path.exists():
        raise click.ClickException(f"Plan CSV does not exist: {plan_path}")
    if not plan_path.is_file():
        raise click.ClickException(f"Plan CSV path is not a file: {plan_path}")

    try:
        with plan_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            raw_fieldnames = reader.fieldnames or []
            fieldnames = [str(name).strip() for name in raw_fieldnames if str(name).strip()]
            if not fieldnames:
                raise click.ClickException(f"Plan CSV is empty: {plan_path}")

            fieldset = set(fieldnames)
            has_executor_headers = {"action", "path", "dest_path"}.issubset(fieldset)
            has_mode_headers = {"source_path", "dest_path", "mode"}.issubset(fieldset)
            if not has_executor_headers and not has_mode_headers:
                raise click.ClickException(
                    "Plan CSV must include either headers "
                    "'action,path,dest_path' (executor format) or "
                    "'source_path,dest_path,mode'."
                )

            summary_rows: list[dict[str, str]] = []
            normalized_rows: list[dict[str, str]] = []
            row_count = 0
            move_count = 0
            copy_count = 0
            delete_count = 0

            for idx, row in enumerate(reader, start=2):
                row_count += 1
                if has_executor_headers:
                    source_path = str(row.get("path") or "").strip()
                    dest_path = str(row.get("dest_path") or "").strip()
                    mode_raw = str(row.get("action") or "").strip()
                    normalized_rows.append(
                        {
                            "action": mode_raw.upper(),
                            "path": source_path,
                            "dest_path": dest_path,
                            "reason": str(row.get("reason") or "").strip(),
                            "db_path": str(row.get("db_path") or "").strip(),
                        }
                    )
                else:
                    source_path = str(row.get("source_path") or "").strip()
                    dest_path = str(row.get("dest_path") or "").strip()
                    mode_raw = str(row.get("mode") or "").strip()
                    normalized_rows.append(
                        {
                            "action": mode_raw.upper(),
                            "path": source_path,
                            "dest_path": dest_path,
                            "reason": str(row.get("reason") or "").strip(),
                            "db_path": str(row.get("db_path") or "").strip(),
                        }
                    )

                if not source_path:
                    raise click.ClickException(f"Plan row {idx} is missing source path")
                if not dest_path:
                    raise click.ClickException(f"Plan row {idx} is missing dest_path")

                mode_class = _classify_mode(mode_raw)
                if mode_class == "move":
                    move_count += 1
                elif mode_class == "copy":
                    copy_count += 1
                elif mode_class == "delete":
                    delete_count += 1

                if len(summary_rows) < 10:
                    summary_rows.append(
                        {
                            "source_path": source_path,
                            "dest_path": dest_path,
                            "mode": _normalize_mode(mode_raw) or "unknown",
                        }
                    )

    except OSError as exc:
        raise click.ClickException(f"Plan CSV is not readable: {plan_path}: {exc}") from exc

    if row_count == 0:
        raise click.ClickException("Plan CSV has zero rows; refusing to execute")

    if has_executor_headers:
        return PlanSummary(
            plan_csv_path=plan_path,
            executor_plan_path=plan_path,
            temp_executor_plan_path=None,
            row_count=row_count,
            move_count=move_count,
            copy_count=copy_count,
            delete_count=delete_count,
            sample_rows=summary_rows,
        )

    temp_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix="tagslut_ops_move_plan_",
        delete=False,
    )
    temp_path = Path(temp_file.name).expanduser().resolve()
    with temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=["action", "path", "dest_path", "reason", "db_path"])
        writer.writeheader()
        for normalized_row in normalized_rows:
            writer.writerow(normalized_row)

    return PlanSummary(
        plan_csv_path=plan_path,
        executor_plan_path=temp_path,
        temp_executor_plan_path=temp_path,
        row_count=row_count,
        move_count=move_count,
        copy_count=copy_count,
        delete_count=delete_count,
        sample_rows=summary_rows,
    )


def _run_executor_subprocess(
    *,
    plan_path: Path,
    db_path: Path,
    dry_run: bool,
) -> ExecutorRunResult:
    cmd = [
        sys.executable,
        "-m",
        "tagslut",
        "execute",
        "move-plan",
        "--plan",
        str(plan_path),
        "--db",
        str(db_path),
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    dry_run_supported = True
    stderr = proc.stderr
    if dry_run and proc.returncode != 0:
        merged = f"{proc.stdout}\n{proc.stderr}"
        if "No such option: --dry-run" in merged:
            dry_run_supported = False
            stderr = f"{stderr}\ndry-run not supported".strip()
    return ExecutorRunResult(
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=stderr,
        receipts=None,
        dry_run_supported=dry_run_supported,
    )


def _run_executor(
    *,
    plan_path: Path,
    db_path: Path,
    dry_run: bool,
) -> ExecutorRunResult:
    try:
        from tagslut.cli.commands.execute import run_execute_move_plan
    except Exception:
        return _run_executor_subprocess(plan_path=plan_path, db_path=db_path, dry_run=dry_run)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    try:
        result = run_execute_move_plan(
            plan_path=plan_path,
            db=db_path,
            dry_run=dry_run,
            verify=False,
            echo=lambda line: stdout_lines.append(str(line)),
        )
        return ExecutorRunResult(
            exit_code=0,
            stdout="\n".join(stdout_lines).strip(),
            stderr="",
            receipts=list(result.receipts),
            dry_run_supported=True,
        )
    except TypeError as exc:
        if dry_run and "dry_run" in str(exc):
            stderr_lines.append("dry-run not supported")
            return ExecutorRunResult(
                exit_code=2,
                stdout="\n".join(stdout_lines).strip(),
                stderr="\n".join(stderr_lines).strip(),
                receipts=None,
                dry_run_supported=False,
            )
        stderr_lines.append(f"{type(exc).__name__}: {exc}")
    except click.ClickException as exc:
        stderr_lines.append(exc.format_message())
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 1
        return ExecutorRunResult(
            exit_code=code,
            stdout="\n".join(stdout_lines).strip(),
            stderr="\n".join(stderr_lines).strip(),
            receipts=None,
            dry_run_supported=True,
        )
    except Exception as exc:
        stderr_lines.append(f"{type(exc).__name__}: {exc}")

    return ExecutorRunResult(
        exit_code=1,
        stdout="\n".join(stdout_lines).strip(),
        stderr="\n".join(stderr_lines).strip(),
        receipts=None,
        dry_run_supported=True,
    )


def _resolve_receipt_path(receipt_out: Path | None, timestamp_slug: str) -> Path:
    if receipt_out is None:
        return (_DEFAULT_RECEIPT_DIR / f"{timestamp_slug}_receipt.json").expanduser().resolve()
    return receipt_out.expanduser().resolve()


def _resolve_plan_archive_dir(plan_archive_dir: Path | None) -> Path:
    if plan_archive_dir is None:
        return _DEFAULT_PLAN_ARCHIVE_DIR.expanduser().resolve()
    return plan_archive_dir.expanduser().resolve()


def _archive_plan_csv(plan_csv_path: Path, archive_dir: Path, timestamp_slug: str) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{timestamp_slug}_{plan_csv_path.name}"
    candidate = archive_dir / base_name
    index = 2
    while candidate.exists():
        candidate = archive_dir / f"{timestamp_slug}_{index}_{plan_csv_path.name}"
        index += 1
    shutil.copy2(plan_csv_path, candidate)
    return candidate


def _git_commit_hash() -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None


def _receipt_sample_from_executor(
    *,
    executor_result: ExecutorRunResult,
    fallback_rows: list[dict[str, str]],
    sample_size: int = 10,
) -> list[dict[str, Any]]:
    if executor_result.receipts:
        sample: list[dict[str, Any]] = []
        for receipt in executor_result.receipts[:sample_size]:
            src = getattr(receipt, "src", None)
            dest_requested = getattr(receipt, "dest_requested", None)
            dest_final = getattr(receipt, "dest_final", None)
            sample.append(
                {
                    "status": str(getattr(receipt, "status", "unknown")),
                    "src": str(src) if src is not None else None,
                    "dest_requested": str(dest_requested) if dest_requested is not None else None,
                    "dest_final": str(dest_final) if dest_final is not None else None,
                }
            )
        return sample
    return [dict(row) for row in fallback_rows[:sample_size]]


def _print_doctor_failure(phase: str, result: DoctorRunResult) -> None:
    if result.stderr.strip():
        click.echo(f"{phase} doctor stderr (last 200 lines):")
        click.echo(_tail_lines(result.stderr))
    if result.stdout.strip():
        click.echo(f"{phase} doctor stdout (last 200 lines):")
        click.echo(_tail_lines(result.stdout))


def register_ops_group(cli: click.Group) -> None:
    @cli.group(name="ops")
    def ops_group() -> None:
        """Operator-grade guarded workflows."""

    @ops_group.command("run-move-plan")
    @click.argument("plan_csv", type=click.Path())
    @click.option("--db", "db_path_arg", type=click.Path(), help="SQLite DB path (or TAGSLUT_DB)")
    @click.option("--strict", is_flag=True, help="Enable strict doctor checks")
    @click.option("--dry-run", is_flag=True, help="Pass through dry-run to move executor")
    @click.option("--postcheck/--no-postcheck", default=True, help="Run postflight doctor checks")
    @click.option(
        "--receipt-out",
        type=click.Path(),
        default=None,
        help="Receipt output path (default: plans/receipts/<timestamp>_receipt.json)",
    )
    @click.option(
        "--plan-archive-dir",
        type=click.Path(file_okay=False),
        default=None,
        help="Plan archive directory (default: plans/archive/)",
    )
    def run_move_plan(
        plan_csv: str,
        db_path_arg: str | None,
        strict: bool,
        dry_run: bool,
        postcheck: bool,
        receipt_out: str | None,
        plan_archive_dir: str | None,
    ) -> None:
        temp_plan_path: Path | None = None
        plan_summary: PlanSummary | None = None
        timestamp_iso = _now_iso()
        timestamp_slug = _timestamp_slug()
        plan_csv_path = Path(plan_csv)
        db_path_value = Path(db_path_arg) if db_path_arg is not None else None
        receipt_out_path = Path(receipt_out) if receipt_out is not None else None
        plan_archive_dir_path = Path(plan_archive_dir) if plan_archive_dir is not None else None

        try:
            try:
                resolution = resolve_cli_env_db_path(
                    db_path_value,
                    purpose="read",
                    source_label="--db",
                )
            except DbResolutionError as exc:
                raise click.ClickException(str(exc)) from exc

            db_path = resolution.path
            click.echo(f"Resolved DB path: {db_path}")

            preflight = _run_doctor(db_path, strict=strict)
            if preflight.exit_code != 0:
                _print_doctor_failure("Preflight", preflight)
                raise click.ClickException("preflight failed; refusing to execute moves")

            click.echo(
                "Preflight doctor OK: "
                f"asset_file_total={preflight.counts['asset_file_total']} "
                f"asset_link_total={preflight.counts['asset_link_total']} "
                f"track_identity_total={preflight.counts['track_identity_total']}"
            )

            plan_summary = _validate_and_summarize_plan(plan_csv_path)
            temp_plan_path = plan_summary.temp_executor_plan_path
            click.echo(
                "Plan summary: "
                f"rows={plan_summary.row_count} "
                f"moves={plan_summary.move_count} "
                f"copies={plan_summary.copy_count} "
                f"deletes={plan_summary.delete_count}"
            )
            if plan_summary.copy_count > 0 or plan_summary.delete_count > 0:
                click.echo("Warning: executor handles MOVE rows only; COPY/DELETE rows are ignored.")

            executor_result = _run_executor(
                plan_path=plan_summary.executor_plan_path,
                db_path=db_path,
                dry_run=dry_run,
            )
            if dry_run and not executor_result.dry_run_supported:
                click.echo("dry-run not supported")

            if executor_result.exit_code != 0:
                if executor_result.stderr.strip():
                    click.echo("Executor stderr (last 200 lines):")
                    click.echo(_tail_lines(executor_result.stderr))
                if executor_result.stdout.strip():
                    click.echo("Executor stdout (last 200 lines):")
                    click.echo(_tail_lines(executor_result.stdout))

            postflight: DoctorRunResult | None = None
            if postcheck:
                postflight = _run_doctor(db_path, strict=strict)
                if postflight.exit_code == 0:
                    click.echo(
                        "Postflight doctor OK: "
                        f"asset_file_total={postflight.counts['asset_file_total']} "
                        f"asset_link_total={postflight.counts['asset_link_total']} "
                        f"track_identity_total={postflight.counts['track_identity_total']}"
                    )
                else:
                    _print_doctor_failure("Postflight", postflight)
            else:
                click.echo("Postflight skipped (--no-postcheck).")

            receipt_path = _resolve_receipt_path(receipt_out_path, timestamp_slug)
            archive_dir = _resolve_plan_archive_dir(plan_archive_dir_path)
            archived_plan = _archive_plan_csv(plan_summary.plan_csv_path, archive_dir, timestamp_slug)

            receipt_payload = {
                "timestamp": timestamp_iso,
                "db_path": str(db_path),
                "plan_csv_path": str(plan_summary.plan_csv_path),
                "plan_row_count": plan_summary.row_count,
                "plan_summary": {
                    "moves": plan_summary.move_count,
                    "copies": plan_summary.copy_count,
                    "deletes": plan_summary.delete_count,
                },
                "executor_exit_code": executor_result.exit_code,
                "doctor_pre_counts": preflight.counts,
                "doctor_post_counts": postflight.counts if postflight is not None else None,
                "sample_moves": _receipt_sample_from_executor(
                    executor_result=executor_result,
                    fallback_rows=plan_summary.sample_rows,
                ),
                "git_commit_hash": _git_commit_hash(),
                "archived_plan_csv_path": str(archived_plan),
                "dry_run": bool(dry_run),
                "dry_run_supported": bool(executor_result.dry_run_supported),
            }

            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(receipt_payload, indent=2, sort_keys=True), encoding="utf-8")

            click.echo(
                "Receipt summary: "
                f"executor_exit_code={executor_result.exit_code} "
                f"plan_rows={plan_summary.row_count}"
            )
            click.echo(f"Receipt written: {receipt_path}")
            click.echo(f"Plan archived: {archived_plan}")

            if postcheck and postflight is not None and postflight.exit_code != 0:
                raise click.ClickException(
                    "postflight failed; system may be inconsistent; inspect receipts/provenance"
                )
            if executor_result.exit_code != 0:
                raise click.ClickException("move-plan execution failed; review diagnostics above")

            click.echo("Move-plan cycle completed.")
        finally:
            if temp_plan_path is not None and temp_plan_path.exists():
                try:
                    temp_plan_path.unlink()
                except OSError:
                    pass

    @ops_group.command("writeback-canonical")
    @click.option("--db", "db_path_arg", type=click.Path(), help="SQLite DB path (or TAGSLUT_DB)")
    @click.option("--path", "path_arg", type=click.Path(), help="Root path or FLAC file to scan")
    @click.option("--m3u", "m3u_arg", type=click.Path(), help="M3U file listing FLAC paths")
    @click.option("--force", is_flag=True, help="Overwrite existing tags")
    @click.option("--execute", is_flag=True, help="Write tags to files")
    @click.option("--progress-interval", default=100, show_default=True, type=int)
    def writeback_canonical(
        db_path_arg: str | None,
        path_arg: str | None,
        m3u_arg: str | None,
        force: bool,
        execute: bool,
        progress_interval: int,
    ) -> None:
        if not path_arg and not m3u_arg:
            raise click.ClickException("Provide --path or --m3u")
        if path_arg and m3u_arg:
            raise click.ClickException("Use only one of --path or --m3u")

        try:
            resolution = resolve_cli_env_db_path(
                Path(db_path_arg) if db_path_arg is not None else None,
                purpose="read",
                source_label="--db",
            )
        except DbResolutionError as exc:
            raise click.ClickException(str(exc)) from exc

        db_path = resolution.path
        if m3u_arg:
            sources = list(iter_flacs_from_m3u(Path(m3u_arg).expanduser().resolve()))
        else:
            sources = list(iter_flacs_from_root(Path(path_arg).expanduser().resolve()))

        if not sources:
            raise click.ClickException("No FLAC files found.")

        with sqlite3.connect(str(db_path)) as conn:
            stats = write_canonical_tags(
                conn,
                sources,
                force=force,
                execute=execute,
                progress_interval=progress_interval,
                echo=click.echo,
            )

        click.echo(f"Scanned:  {stats.scanned}")
        click.echo(f"Updated:  {stats.updated}")
        click.echo(f"Skipped:  {stats.skipped}")
        click.echo(f"Missing:  {stats.missing}")
        if not execute:
            click.echo("DRY-RUN: use --execute to write tags")
