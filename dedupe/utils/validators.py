"""
Validators for pre-flight checks.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from dedupe.utils.db import resolve_db_path, open_db


class PreFlightValidator:
    def __init__(
        self,
        quarantine_root: Path | None,
        plan_path: Path | None,
        db_path: str | None,
        execute: bool
    ):
        self.quarantine_root = quarantine_root
        self.plan_path = plan_path
        self.db_path = db_path
        self.execute = execute
        self.errors: list[str] = []
        self.total_size = 0

    def validate(self) -> bool:
        self._validate_quarantine_root()
        self._validate_plan_path()
        self._validate_db_path()
        self._validate_db_integrity()
        if self.execute:
            self._validate_disk_space()
            self._validate_source_files()
        # If quarantine root or plan file is missing, validation should fail
        if not self.quarantine_root or (self.plan_path and not self.plan_path.exists()):
            return False
        return not self.errors

    def _validate_quarantine_root(self) -> None:
        if not self.quarantine_root:
            self.errors.append("Quarantine root not provided. Set --quarantine-root or VOLUME_QUARANTINE env var.")
            return

        if not self.quarantine_root.exists():
            self.errors.append(f"Quarantine root does not exist: {self.quarantine_root}")
            return
        if not os.access(self.quarantine_root, os.W_OK):
            self.errors.append(f"Quarantine root is not writable: {self.quarantine_root}")

    def _validate_plan_path(self) -> None:
        if self.plan_path and not self.plan_path.exists():
            self.errors.append(f"Plan file does not exist: {self.plan_path}")

    def _validate_db_path(self) -> None:
        if not self.db_path:
            self.errors.append("Database path not provided. Set --db or DB_PATH env var.")
            return

        resolution = resolve_db_path(self.db_path, purpose="write", allow_repo_db=False, source_label="cli")
        if not resolution.path.exists():
            self.errors.append(f"Database file does not exist: {resolution.path}")

    def _validate_db_integrity(self) -> None:
        if not self.db_path:
            return

        resolution = resolve_db_path(self.db_path, purpose="write", allow_repo_db=False, source_label="cli")
        if not resolution.path.exists():
            return
            
        try:
            conn = open_db(resolution, row_factory=False)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            if result and result[0] != "ok":
                self.errors.append(f"Database integrity check failed: {result[0]}")
        except Exception as e:
            self.errors.append(f"Database integrity check failed with error: {e}")
        finally:
            if conn:
                conn.close()

    def _validate_source_files(self) -> None:
        # This check is specific to apply_removals and will be kept there.
        pass

    def _validate_disk_space(self) -> None:
        if not self.plan_path or not self.quarantine_root:
            return
        if not self.plan_path.exists():
            self.errors.append(f"Plan file does not exist: {self.plan_path}")
            return
        if not self.quarantine_root.exists():
            # Error already appended in _validate_quarantine_root
            return

        from dedupe.utils.plan import load_plan_rows
        try:
            rows = load_plan_rows(self.plan_path)
        except FileNotFoundError:
            self.errors.append(f"Plan file does not exist: {self.plan_path}")
            return
        for row in rows:
            try:
                self.total_size += Path(row.path).stat().st_size
            except FileNotFoundError:
                pass
        free_space = shutil.disk_usage(self.quarantine_root).free
        if self.total_size > free_space:
            self.errors.append(
                f"Not enough disk space. Required: {self.total_size / (1024**3):.2f} GB, "
                f"Available: {free_space / (1024**3):.2f} GB"
            )

    def get_errors(self) -> list[str]:
        return self.errors

