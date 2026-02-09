"""Centralized move executor with structured receipts and verification hooks."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

EXECUTOR_CONTRACT_VERSION = "move_exec.v2"

MoveStatus = Literal["dry_run", "moved", "skip_missing", "skip_dest_exists", "error"]
CollisionPolicy = Literal["abort", "dedupe", "skip"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="replace")).hexdigest()[:8]


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _same_filesystem(src: Path, dest: Path) -> bool:
    try:
        return os.stat(src).st_dev == os.stat(dest.parent).st_dev
    except Exception:
        return False


def _move_no_overwrite(src: Path, dest: Path) -> None:
    if dest.exists():
        raise FileExistsError(f"Destination exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if _same_filesystem(src, dest):
            os.replace(src, dest)
        else:
            shutil.move(str(src), str(dest))
    except OSError as exc:
        if getattr(exc, "errno", None) == errno.EXDEV:
            shutil.move(str(src), str(dest))
            return
        raise


def _dedupe_destination(dest: Path, src: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    src_hash = _short_hash(str(src))
    candidate = dest.with_name(f"{stem}__dup_{src_hash}{suffix}")
    if not candidate.exists():
        return candidate
    for i in range(2, 1000):
        candidate = dest.with_name(f"{stem}__dup_{src_hash}_{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not resolve collision for destination: {dest}")


@dataclass(frozen=True)
class MoveReceipt:
    """Structured move execution receipt."""

    status: MoveStatus
    src: Path
    dest_requested: Path
    execute: bool
    collision_policy: CollisionPolicy
    started_at: str
    completed_at: str
    dest_final: Path | None = None
    source_size: int | None = None
    dest_size: int | None = None
    verification: str | None = None
    verification_ok: bool = True
    verification_errors: tuple[str, ...] = ()
    error: str | None = None
    executor_contract: str = EXECUTOR_CONTRACT_VERSION
    content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "executor_contract": self.executor_contract,
            "status": self.status,
            "src": str(self.src),
            "dest_requested": str(self.dest_requested),
            "execute": bool(self.execute),
            "collision_policy": self.collision_policy,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "verification_ok": bool(self.verification_ok),
            "verification_errors": list(self.verification_errors),
            "content_hash": self.content_hash,
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

    def to_event_fields(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "result": self.status,
            "executor_contract": self.executor_contract,
            "receipt_hash": self.content_hash,
            "verification_ok": self.verification_ok,
        }
        if self.dest_final is not None:
            payload["dest_final"] = str(self.dest_final)
        if self.source_size is not None:
            payload["source_size"] = int(self.source_size)
        if self.dest_size is not None:
            payload["dest_size"] = int(self.dest_size)
        if self.verification is not None:
            payload["verification"] = self.verification
        if self.verification_errors:
            payload["verification_errors"] = list(self.verification_errors)
        if self.error is not None:
            payload["error"] = self.error
        return payload


def _build_receipt(
    *,
    status: MoveStatus,
    src: Path,
    dest_requested: Path,
    execute: bool,
    collision_policy: CollisionPolicy,
    started_at: str,
    dest_final: Path | None = None,
    source_size: int | None = None,
    dest_size: int | None = None,
    verification: str | None = None,
    verification_ok: bool = True,
    verification_errors: list[str] | None = None,
    error: str | None = None,
) -> MoveReceipt:
    completed_at = _now_iso()
    proto_payload = {
        "executor_contract": EXECUTOR_CONTRACT_VERSION,
        "status": status,
        "src": str(src),
        "dest_requested": str(dest_requested),
        "execute": bool(execute),
        "collision_policy": collision_policy,
        "started_at": started_at,
        "completed_at": completed_at,
        "dest_final": str(dest_final) if dest_final is not None else None,
        "source_size": source_size,
        "dest_size": dest_size,
        "verification": verification,
        "verification_ok": bool(verification_ok),
        "verification_errors": verification_errors or [],
        "error": error,
    }
    return MoveReceipt(
        status=status,
        src=src,
        dest_requested=dest_requested,
        execute=execute,
        collision_policy=collision_policy,
        started_at=started_at,
        completed_at=completed_at,
        dest_final=dest_final,
        source_size=source_size,
        dest_size=dest_size,
        verification=verification,
        verification_ok=bool(verification_ok),
        verification_errors=tuple(verification_errors or ()),
        error=error,
        content_hash=_stable_hash(proto_payload),
    )


def verify_receipt(receipt: MoveReceipt) -> tuple[bool, list[str]]:
    """Verify postconditions encoded in a move receipt."""

    errors: list[str] = []
    src_exists = receipt.src.exists()
    dest_exists = receipt.dest_final.exists() if receipt.dest_final is not None else False

    if receipt.status == "moved":
        if receipt.dest_final is None:
            errors.append("dest_final_missing")
        if src_exists:
            errors.append("source_still_exists")
        if not dest_exists:
            errors.append("dest_missing")
        if (
            receipt.source_size is not None
            and receipt.dest_size is not None
            and receipt.source_size != receipt.dest_size
        ):
            errors.append("size_mismatch")
    elif receipt.status == "dry_run":
        if not src_exists:
            errors.append("source_missing_for_dry_run")
    elif receipt.status == "skip_missing":
        if src_exists:
            errors.append("source_exists_for_skip_missing")

    return (len(errors) == 0), errors


def execute_move(
    src: Path,
    dest: Path,
    *,
    execute: bool,
    collision_policy: CollisionPolicy = "skip",
) -> MoveReceipt:
    """Execute one move action with deterministic safety checks."""

    if collision_policy not in {"skip", "dedupe", "abort"}:
        raise ValueError(f"Unsupported collision_policy: {collision_policy}")

    started_at = _now_iso()
    src = Path(src)
    dest = Path(dest)

    if not src.exists():
        return _build_receipt(
            status="skip_missing",
            src=src,
            dest_requested=dest,
            execute=execute,
            collision_policy=collision_policy,
            started_at=started_at,
            error="source_missing",
            verification_ok=True,
        )

    dest_final = dest
    if dest_final.exists():
        if collision_policy in {"skip", "abort"}:
            status: MoveStatus = "skip_dest_exists"
            err = "destination_exists_abort" if collision_policy == "abort" else None
            return _build_receipt(
                status=status,
                src=src,
                dest_requested=dest,
                execute=execute,
                collision_policy=collision_policy,
                started_at=started_at,
                dest_final=dest_final,
                error=err,
                verification_ok=True,
            )
        dest_final = _dedupe_destination(dest_final, src)

    try:
        source_size = src.stat().st_size
    except Exception as exc:
        return _build_receipt(
            status="error",
            src=src,
            dest_requested=dest,
            execute=execute,
            collision_policy=collision_policy,
            started_at=started_at,
            dest_final=dest_final,
            error=f"source_stat_failed: {type(exc).__name__}: {exc}",
            verification_ok=False,
            verification_errors=["source_stat_failed"],
        )

    if not execute:
        return _build_receipt(
            status="dry_run",
            src=src,
            dest_requested=dest,
            execute=execute,
            collision_policy=collision_policy,
            started_at=started_at,
            dest_final=dest_final,
            source_size=source_size,
            verification="size_eq",
            verification_ok=True,
        )

    try:
        _move_no_overwrite(src, dest_final)
    except FileExistsError:
        if collision_policy == "dedupe":
            try:
                dest_final = _dedupe_destination(dest_final, src)
                _move_no_overwrite(src, dest_final)
            except Exception as exc:
                return _build_receipt(
                    status="error",
                    src=src,
                    dest_requested=dest,
                    execute=execute,
                    collision_policy=collision_policy,
                    started_at=started_at,
                    dest_final=dest_final,
                    source_size=source_size,
                    error=f"{type(exc).__name__}: {exc}",
                    verification_ok=False,
                    verification_errors=["move_failed"],
                )
        else:
            return _build_receipt(
                status="skip_dest_exists",
                src=src,
                dest_requested=dest,
                execute=execute,
                collision_policy=collision_policy,
                started_at=started_at,
                dest_final=dest_final,
                source_size=source_size,
                verification_ok=True,
            )
    except Exception as exc:
        return _build_receipt(
            status="error",
            src=src,
            dest_requested=dest,
            execute=execute,
            collision_policy=collision_policy,
            started_at=started_at,
            dest_final=dest_final,
            source_size=source_size,
            error=f"{type(exc).__name__}: {exc}",
            verification_ok=False,
            verification_errors=["move_failed"],
        )

    try:
        dest_size = dest_final.stat().st_size
    except Exception as exc:
        return _build_receipt(
            status="error",
            src=src,
            dest_requested=dest,
            execute=execute,
            collision_policy=collision_policy,
            started_at=started_at,
            dest_final=dest_final,
            source_size=source_size,
            error=f"dest_stat_failed: {type(exc).__name__}: {exc}",
            verification_ok=False,
            verification_errors=["dest_stat_failed"],
        )

    receipt = _build_receipt(
        status="moved",
        src=src,
        dest_requested=dest,
        execute=execute,
        collision_policy=collision_policy,
        started_at=started_at,
        dest_final=dest_final,
        source_size=source_size,
        dest_size=dest_size,
        verification="size_eq",
        verification_ok=True,
    )
    is_valid, issues = verify_receipt(receipt)
    if is_valid:
        return receipt
    return _build_receipt(
        status="error",
        src=src,
        dest_requested=dest,
        execute=execute,
        collision_policy=collision_policy,
        started_at=started_at,
        dest_final=dest_final,
        source_size=source_size,
        dest_size=dest_size,
        verification="size_eq",
        verification_ok=False,
        verification_errors=issues,
        error=f"verification_failed:{','.join(issues)}",
    )
