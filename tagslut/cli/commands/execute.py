from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import click

from tagslut.cli.runtime import run_python_script, WRAPPER_CONTEXT


@dataclass(frozen=True)
class _MovePlanRow:
    src: Path
    dest: Path
    reason: str
    db_where_path: str | None


def _load_move_plan_rows(plan_path: Path) -> list[_MovePlanRow]:
    rows: list[_MovePlanRow] = []
    with plan_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise click.ClickException(f"Plan CSV is empty: {plan_path}")
        if "action" not in reader.fieldnames or "path" not in reader.fieldnames:
            raise click.ClickException("Plan CSV must include 'action' and 'path' columns")
        for idx, row in enumerate(reader, start=2):
            action = str(row.get("action") or "").strip().upper()
            if action != "MOVE":
                continue
            src_value = str(row.get("path") or "").strip()
            dest_value = str(row.get("dest_path") or "").strip()
            if not src_value:
                raise click.ClickException(f"Row {idx}: missing path")
            if not dest_value:
                raise click.ClickException(f"Row {idx}: missing dest_path for MOVE action")
            rows.append(
                _MovePlanRow(
                    src=Path(src_value).expanduser(),
                    dest=Path(dest_value).expanduser(),
                    reason=str(row.get("reason") or "").strip(),
                    db_where_path=(str(row.get("db_path") or "").strip() or None),
                )
            )
    return rows


@dataclass(frozen=True)
class ExecuteMovePlanResult:
    receipts: list[object]
    db_path: Path | None
    counts: dict[str, int]


def run_execute_move_plan(
    *,
    plan_path: Path,
    db: Path | None,
    dry_run: bool,
    verify: bool,
    echo: Callable[[str], None] = click.echo,
) -> ExecuteMovePlanResult:
    """Run execute move-plan core flow and return structured results."""
    from tagslut.exec.engine import MovePlanItem, execute_move_plan as run_move_plan
    from tagslut.exec.receipts import record_move_receipt, update_legacy_path_with_receipt
    from tagslut.storage.schema import get_connection, init_db
    from tagslut.storage.v3 import ensure_move_plan
    from tagslut.utils.db import resolve_db_path

    resolved_plan_path = plan_path.expanduser().resolve()
    move_rows = _load_move_plan_rows(resolved_plan_path)
    if not move_rows:
        echo("No MOVE rows found in plan.")
        return ExecuteMovePlanResult(
            receipts=[],
            db_path=None,
            counts={"moved": 0, "dry_run": 0, "skip_missing": 0, "skip_dest_exists": 0, "error": 0},
        )

    plan_items = [MovePlanItem(src=row.src, dest=row.dest) for row in move_rows]
    receipts = run_move_plan(plan_items, execute=not dry_run, collision_policy="skip")

    db_path: Path | None = None
    if db is not None:
        db_path = resolve_db_path(str(db), purpose="write", allow_create=True).path
        conn = get_connection(str(db_path), purpose="write", allow_create=True)
        init_db(conn)
        try:
            plan_id = ensure_move_plan(
                conn,
                plan_key=f"execute.move-plan:{resolved_plan_path}",
                plan_type="move_from_plan",
                plan_path=str(resolved_plan_path),
                policy_version="execute.move-plan.v1",
                context={"dry_run": bool(dry_run)},
            )
            for row, receipt in zip(move_rows, receipts):
                write_result = record_move_receipt(
                    conn,
                    receipt=receipt,
                    plan_id=plan_id,
                    action="MOVE",
                    zone="staging",
                    mgmt_status="moved_from_plan",
                    script_name="tagslut.cli.commands.execute",
                    details={"reason": row.reason},
                )
                if receipt.status == "moved":
                    update_legacy_path_with_receipt(
                        conn,
                        move_execution_id=write_result.move_execution_id,
                        receipt=receipt,
                        zone="staging",
                        mgmt_status="moved_from_plan",
                        where_path=row.db_where_path,
                    )
            conn.commit()
        finally:
            conn.close()

    counts = {"moved": 0, "dry_run": 0, "skip_missing": 0, "skip_dest_exists": 0, "error": 0}
    for receipt in receipts:
        counts[receipt.status] += 1

    echo(f"Plan: {resolved_plan_path}")
    echo(f"Rows: {len(receipts)}")
    echo(f"Moved: {counts['moved']}")
    echo(f"Dry-run: {counts['dry_run']}")
    echo(f"Skipped (missing): {counts['skip_missing']}")
    echo(f"Skipped (dest exists): {counts['skip_dest_exists']}")
    echo(f"Errors: {counts['error']}")
    if db_path is not None:
        echo(f"DB: {db_path}")

    if verify:
        if db_path is None:
            raise click.ClickException("--verify requires --db")
        run_python_script("scripts/validate_v3_dual_write_parity.py", ("--db", str(db_path)))

    return ExecuteMovePlanResult(receipts=list(receipts), db_path=db_path, counts=counts)


def register_execute_group(cli: click.Group) -> None:
    @cli.group(name="execute")
    def execute_group():  # type: ignore  # TODO: mypy-strict
        """Canonical execution commands."""

    @execute_group.command("move-plan")
    @click.option(
        "--plan",
        "plan_path",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=Path),  # type: ignore  # TODO: mypy-strict
        help="Plan CSV path",
    )
    @click.option("--db", type=click.Path(path_type=Path), help="SQLite DB path (for receipt writeback)")
    @click.option("--dry-run", is_flag=True, help="Plan only; do not move files")
    @click.option("--verify", is_flag=True, help="Run parity checks after execution")
    def execute_move_plan(plan_path: Path, db: Path | None, dry_run: bool, verify: bool) -> None:
        """Execute move actions from a plan CSV."""
        run_execute_move_plan(
            plan_path=plan_path,
            db=db,
            dry_run=dry_run,
            verify=verify,
        )

    @execute_group.command("quarantine-plan", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def execute_quarantine_plan(args):  # type: ignore  # TODO: mypy-strict
        """Execute quarantine move actions from a plan CSV."""
        run_python_script("tools/review/quarantine_from_plan.py", args)

    @execute_group.command("promote-tags", context_settings=WRAPPER_CONTEXT)
    @click.argument("args", nargs=-1, type=click.UNPROCESSED)
    def execute_promote_tags(args):  # type: ignore  # TODO: mypy-strict
        """Execute promote-by-tags move workflow."""
        run_python_script("tools/review/promote_by_tags.py", args)
