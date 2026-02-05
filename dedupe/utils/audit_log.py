"""Lightweight JSONL audit logging helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

DEFAULT_LOG_DIR = Path.home() / ".dedupe" / "logs"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_log_path(kind: str, default_dir: Path | None = None) -> Path:
    """Resolve a log path for a given event kind."""
    base_dir = default_dir or Path(os.getenv("DEDUPE_LOG_DIR", DEFAULT_LOG_DIR))
    base_dir = base_dir.expanduser()
    return base_dir / f"{kind}.jsonl"


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """Append a single JSON object as a JSONL line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True)
        handle.write("\n")
