"""Structured JSON logging with context."""

import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class LogContext:
    """Structured log context."""
    operation: str
    file_path: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    volume: Optional[str] = None
    status: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StructuredLogger:
    """JSON logger for structured logs."""

    def __init__(self, name: str, level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self._context_stack: list = []  # type: ignore  # TODO: mypy-strict

    def log_operation(self, context: LogContext) -> None:
        """Log operation with structured context."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "context": context.to_dict(),
        }
        self.logger.info(json.dumps(log_data))

    def log_error(self, error_type: str, message: str, file_path: Optional[str] = None) -> None:
        """Log error with categorization."""
        context = LogContext(
            operation="error",
            error_type=error_type,
            error_message=message,
            file_path=file_path,
            status="error",
        )
        self.log_operation(context)

    def extract_failed_files(self, log_file: str) -> list:  # type: ignore  # TODO: mypy-strict
        """Extract failed file paths from log."""
        failed_files = []
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ctx = entry.get("context", {})
                        if ctx.get("status") == "error" and ctx.get("file_path"):
                            failed_files.append(ctx["file_path"])
                    except json.JSONDecodeError:
                        continue
        except IOError as e:
            self.logger.error(f"Failed to read log: {e}")
        return failed_files
