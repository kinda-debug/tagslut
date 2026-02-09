"""Helpers for writing move receipts into v3 execution/provenance tables."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dedupe.exec.engine import MoveReceipt
from dedupe.storage.schema import V3_MOVE_EXECUTION_TABLE
from dedupe.storage.v3 import (
    insert_move_execution,
    move_asset_path,
    record_provenance_event,
    upsert_asset_file,
)


@dataclass(frozen=True)
class ReceiptWriteResult:
    """Database IDs generated while recording one execution receipt."""

    asset_id: int | None
    move_execution_id: int
    provenance_event_id: int


def record_move_receipt(
    conn: sqlite3.Connection,
    *,
    receipt: MoveReceipt,
    plan_id: int | None,
    action: str | None,
    zone: str | None,
    mgmt_status: str | None,
    script_name: str,
    details: dict[str, Any] | None = None,
) -> ReceiptWriteResult:
    """Persist receipt outcome in v3 move/provenance tables."""

    src = str(receipt.src)
    dest = str(receipt.dest_final or receipt.dest_requested)
    row_details = dict(details or {})
    row_details["receipt_hash"] = receipt.content_hash
    row_details["executor_contract"] = receipt.executor_contract
    row_details["verification_ok"] = bool(receipt.verification_ok)
    if receipt.verification_errors:
        row_details["verification_errors"] = list(receipt.verification_errors)

    if receipt.status == "moved":
        asset_id = move_asset_path(
            conn,
            source_path=src,
            dest_path=dest,
            update_fields={
                "size_bytes": receipt.dest_size or receipt.source_size,
                "zone": zone,
                "mgmt_status": mgmt_status,
            },
        )
    else:
        asset_id = upsert_asset_file(
            conn,
            path=src,
            size_bytes=receipt.source_size,
            zone=zone,
            mgmt_status=mgmt_status,
        )

    move_execution_id = insert_move_execution(
        conn,
        plan_id=plan_id,
        asset_id=asset_id,
        source_path=src,
        dest_path=dest,
        action=action,
        status=receipt.status,
        verification=receipt.verification,
        error=receipt.error,
        details=row_details,
        executed_at=receipt.completed_at,
    )
    provenance_event_id = record_provenance_event(
        conn,
        event_type="move_execution",
        status=receipt.status,
        asset_id=asset_id,
        move_plan_id=plan_id,
        move_execution_id=move_execution_id,
        source_path=src,
        dest_path=dest,
        details={"script": script_name, **row_details},
        event_time=receipt.completed_at,
    )
    return ReceiptWriteResult(
        asset_id=asset_id,
        move_execution_id=move_execution_id,
        provenance_event_id=provenance_event_id,
    )


def update_legacy_path_with_receipt(
    conn: sqlite3.Connection,
    *,
    move_execution_id: int,
    receipt: MoveReceipt,
    zone: str,
    mgmt_status: str,
    where_path: str | Path | None = None,
) -> None:
    """Update legacy files.path only when a moved receipt exists in v3 table."""

    if receipt.status != "moved":
        raise ValueError("Cannot mutate legacy files.path without a moved receipt")
    if receipt.dest_final is None:
        raise ValueError("Cannot mutate legacy files.path without dest_final")

    row = conn.execute(
        f"SELECT status FROM {V3_MOVE_EXECUTION_TABLE} WHERE id = ?",
        (move_execution_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("move_execution receipt row not found")
    status = str(row[0]).strip().lower()
    if status != "moved":
        raise RuntimeError(f"move_execution receipt status must be moved, got {status}")

    src = str(where_path or receipt.src)
    dest = str(receipt.dest_final)
    conn.execute(
        """
        UPDATE files
        SET original_path = COALESCE(original_path, path),
            path = ?,
            zone = ?,
            mgmt_status = ?
        WHERE path = ?
        """,
        (dest, zone, mgmt_status, src),
    )
