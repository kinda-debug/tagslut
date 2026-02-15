"""Centralized execution APIs and legacy compatibility adapters."""

from tagslut.exec.compat import ADAPTER_CONTRACT_VERSION, MoveExecutionResult, execute_move_action
from tagslut.exec.engine import (
    CollisionPolicy,
    EXECUTOR_CONTRACT_VERSION,
    MoveReceipt,
    MoveStatus,
    execute_move,
    verify_receipt,
)
from tagslut.exec.receipts import (
    ReceiptWriteResult,
    record_move_receipt,
    update_legacy_path_with_receipt,
)

__all__ = [
    "ADAPTER_CONTRACT_VERSION",
    "CollisionPolicy",
    "EXECUTOR_CONTRACT_VERSION",
    "MoveExecutionResult",
    "MoveReceipt",
    "MoveStatus",
    "ReceiptWriteResult",
    "execute_move",
    "execute_move_action",
    "record_move_receipt",
    "update_legacy_path_with_receipt",
    "verify_receipt",
]
