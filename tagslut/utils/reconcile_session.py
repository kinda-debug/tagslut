from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


_RECONCILE_CHECKPOINT_RE = re.compile(r"^reconcile_(\d{8})_(\d{2})(?:_FINAL)?\.json$")


@dataclass(frozen=True)
class ReconcileCheckpoint:
    path: Path
    data: dict[str, Any]

    @property
    def run_id(self) -> str:
        return str(self.data.get("session_run_id") or "")

    @property
    def completed_tasks(self) -> list[int]:
        raw = self.data.get("completed_tasks") or []
        out: list[int] = []
        for v in raw:
            try:
                out.append(int(v))
            except Exception:
                continue
        return sorted(set(out))


def _now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _checkpoint_filename(*, suffix: str = "") -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H")
    tail = f"_{suffix}" if suffix else ""
    return f"reconcile_{stamp}{tail}.json"


def find_latest_checkpoint(checkpoints_dir: Path) -> ReconcileCheckpoint | None:
    if not checkpoints_dir.exists():
        return None
    candidates: list[Path] = []
    for path in checkpoints_dir.glob("reconcile_*.json"):
        if not path.is_file():
            continue
        if not _RECONCILE_CHECKPOINT_RE.match(path.name):
            continue
        candidates.append(path)
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return ReconcileCheckpoint(path=latest, data=data)


def find_latest_checkpoint_for_run_id(
    checkpoints_dir: Path, *, run_id: str
) -> ReconcileCheckpoint | None:
    if not checkpoints_dir.exists():
        return None
    candidates: list[Path] = []
    for path in checkpoints_dir.glob("reconcile_*.json"):
        if not path.is_file():
            continue
        if not _RECONCILE_CHECKPOINT_RE.match(path.name):
            continue
        candidates.append(path)
    if not candidates:
        return None
    # Prefer newest-by-mtime among those matching this run id.
    matching: list[ReconcileCheckpoint] = []
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("session_run_id") or "") != run_id:
            continue
        matching.append(ReconcileCheckpoint(path=path, data=data))
    if not matching:
        return None
    return max(matching, key=lambda ck: ck.path.stat().st_mtime)


def ensure_session_run_id(
    *,
    run_id_arg: str,
    checkpoints_dir: Path,
) -> tuple[str, ReconcileCheckpoint | None]:
    """Return (run_id, latest_checkpoint_if_any).

    If run_id_arg is empty and a reconcile checkpoint exists, reuses the checkpoint run id.
    Otherwise generates a new uuid4.
    """
    latest_any = find_latest_checkpoint(checkpoints_dir)
    if run_id_arg.strip():
        selected = run_id_arg.strip()
        return selected, find_latest_checkpoint_for_run_id(checkpoints_dir, run_id=selected) or latest_any
    if latest_any is not None and latest_any.run_id:
        selected = latest_any.run_id
        return selected, find_latest_checkpoint_for_run_id(checkpoints_dir, run_id=selected) or latest_any
    selected = str(uuid.uuid4())
    return selected, latest_any


def task_done(checkpoint: ReconcileCheckpoint | None, task_number: int) -> bool:
    if checkpoint is None:
        return False
    return int(task_number) in set(checkpoint.completed_tasks)


def format_completed_tasks(checkpoint: ReconcileCheckpoint | None) -> str:
    if checkpoint is None:
        return "(none)"
    tasks = checkpoint.completed_tasks
    return " ".join(str(n) for n in tasks) if tasks else "(none)"


def update_checkpoint(
    *,
    checkpoints_dir: Path,
    run_id: str,
    task_number: int,
    notes: str,
    status: str = "done",
) -> Path:
    """Upsert a reconcile checkpoint for this run_id and write it to disk."""
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    # Prefer the most recent checkpoint for this run_id (if any), else seed from the latest overall.
    prior: ReconcileCheckpoint | None = None
    for path in sorted(checkpoints_dir.glob("reconcile_*.json"), key=lambda p: p.stat().st_mtime):
        if not path.is_file():
            continue
        if not _RECONCILE_CHECKPOINT_RE.match(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict) and str(data.get("session_run_id") or "") == run_id:
            prior = ReconcileCheckpoint(path=path, data=data)

    base: dict[str, Any] = prior.data.copy() if prior is not None else {}
    completed: set[int] = set()
    for v in base.get("completed_tasks") or []:
        try:
            completed.add(int(v))
        except Exception:
            continue
    completed.add(int(task_number))

    summaries = base.get("task_summaries") or {}
    if not isinstance(summaries, dict):
        summaries = {}
    summaries[str(int(task_number))] = {"status": status, "notes": notes}

    updated: dict[str, Any] = {
        "session_run_id": run_id,
        "completed_tasks": sorted(completed),
        "task_summaries": summaries,
        "last_updated": _now_local_iso(),
    }

    out_path = checkpoints_dir / _checkpoint_filename()
    out_path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path
