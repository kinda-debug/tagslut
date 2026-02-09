"""Compatibility adapter for legacy callers now backed by central executor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dedupe.exec.engine import execute_move

ADAPTER_CONTRACT_VERSION = "move_exec_adapter.v1"

MoveResult = Literal["dry_run", "moved", "skip_missing", "skip_dest_exists", "error"]
CollisionPolicy = Literal["skip", "dedupe"]


@dataclass(frozen=True)
class MoveExecutionResult:
    """Structured result for one requested move action."""

    result: MoveResult
    src: Path
    dest_requested: Path
    dest_final: Path | None = None
    source_size: int | None = None
    dest_size: int | None = None
    verification: str | None = None
    error: str | None = None

    def to_event_fields(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "result": self.result,
            "executor_contract": ADAPTER_CONTRACT_VERSION,
        }
        if self.dest_final is not None:
            payload["dest_final"] = str(self.dest_final)
        if self.source_size is not None:
            payload["source_size"] = int(self.source_size)
        if self.dest_size is not None:
            payload["dest_size"] = int(self.dest_size)
        if self.verification is not None:
            payload["verification"] = self.verification
        if self.error is not None:
            payload["error"] = self.error
        return payload


def execute_move_action(
    src: Path,
    dest: Path,
    *,
    execute: bool,
    collision_policy: CollisionPolicy = "skip",
) -> MoveExecutionResult:
    """Execute one move action while preserving legacy return shape."""

    receipt = execute_move(
        src,
        dest,
        execute=execute,
        collision_policy=collision_policy,
    )
    return MoveExecutionResult(
        result=receipt.status,
        src=Path(receipt.src),
        dest_requested=Path(receipt.dest_requested),
        dest_final=Path(receipt.dest_final) if receipt.dest_final is not None else None,
        source_size=receipt.source_size,
        dest_size=receipt.dest_size,
        verification=receipt.verification,
        error=receipt.error,
    )
