from __future__ import annotations

import os
from pathlib import Path


class PreFlightValidator:
    def __init__(self, quarantine_root: Path, plan_path: Path, db_path: str | None, execute: bool):
        self.quarantine_root = quarantine_root
        self.plan_path = plan_path
        self.db_path = db_path
        self.execute = execute
        self._errors: list[str] = []

    def get_errors(self) -> list[str]:
        return self._errors

    def validate(self) -> bool:
        self._errors = []

        # Validate plan file
        if not self.plan_path.exists():
            self._errors.append(f"Plan file not found: {self.plan_path}")
        elif not os.access(self.plan_path, os.R_OK):
            self._errors.append(f"Plan file not readable: {self.plan_path}")

        # Validate quarantine root
        if self.execute:
            if self.quarantine_root.exists():
                if not self.quarantine_root.is_dir():
                    self._errors.append(
                        f"Quarantine root exists but is not a directory: {self.quarantine_root}")
                elif not os.access(self.quarantine_root, os.W_OK):
                    self._errors.append(f"Quarantine root is not writable: {self.quarantine_root}")
            else:
                # Check if parent is writable so we can create it
                parent = self.quarantine_root.parent
                if not parent.exists():
                    self._errors.append(
                        f"Quarantine root's parent directory does not exist: {parent}")
                elif not os.access(parent, os.W_OK):
                    self._errors.append(
                        f"Quarantine root's parent directory is not writable: {parent}")

        return not self._errors
