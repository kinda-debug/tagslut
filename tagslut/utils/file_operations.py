from __future__ import annotations
import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from tagslut.utils.console_ui import ConsoleUI
from tagslut.utils.safety_gates import SafetyGates
from tagslut.utils.audit_log import append_jsonl, now_iso, resolve_log_path


def get_sha256(file_path: Path) -> str:
    """Calculates the SHA256 checksum of a file."""
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


class FileOperations:
    """
    A centralized class for performing safe file system operations.
    """

    def __init__(
        self,
        ui: ConsoleUI,
        gates: SafetyGates,
        dry_run: bool = True,
        quiet: bool = False,
        audit_log_path: Path | None = None,
    ):
        self.ui = ui
        self.gates = gates
        self.dry_run = dry_run
        self.quiet = quiet  # Suppress per-file output (caller handles it)
        if audit_log_path is None:
            self.audit_log_path = resolve_log_path(
                "file_move",
                default_dir=Path("artifacts") / "logs",
            )
        else:
            self.audit_log_path = Path(audit_log_path).expanduser()

    def _log(self, message: str):  # type: ignore  # TODO: mypy-strict
        """Internal logging that respects quiet mode."""
        if not self.quiet:
            self.ui.print(message)

    def _write_move_audit(self, payload: dict[str, Any]) -> bool:
        try:
            append_jsonl(self.audit_log_path, payload)
            return True
        except Exception as exc:
            self.ui.error(f"Failed to write move audit log {self.audit_log_path}: {exc}")
            return False

    def safe_copy(
        self,
        source: Path,
        destination: Path,
        verify_checksum: bool = True,
        skip_confirmation: bool = False,
    ) -> bool:
        """
        Copy operations are disabled by policy. This method exists only
        for backward compatibility and will perform a move instead.
        """
        self.ui.warning("Copy is disabled (move-only policy). Performing move instead.")
        return self.safe_move(
            source,
            destination,
            verify_checksum=verify_checksum,
            skip_confirmation=skip_confirmation,
        )

    def _copy_to_temp(
        self,
        source: Path,
        temp_path: Path,
        verify_checksum: bool = True,
        source_checksum: str | None = None,
    ) -> bool:
        """Copy to a temp path and verify integrity."""
        shutil.copy2(source, temp_path)

        if temp_path.stat().st_size != source.stat().st_size:
            raise IOError("Temp file size does not match source.")

        if verify_checksum:
            checksum = source_checksum or get_sha256(source)
            temp_checksum = get_sha256(temp_path)
            if checksum != temp_checksum:
                raise IOError(f"Temp checksum mismatch. Expected {checksum}, got {temp_checksum}")

        return True

    def safe_move(
        self,
        source: Path,
        destination: Path,
        verify_checksum: bool = True,
        confirmation_phrase: str = "I understand this is a move operation.",
        skip_confirmation: bool = False,
        allow_overwrite: bool = False,
    ) -> bool:
        """
        Safely moves a file from source to destination using move-only semantics.
        A temporary file is created for verification and removed after success.
        """
        source = Path(source)
        destination = Path(destination)
        verification = "size_eq+checksum_eq" if verify_checksum else "size_eq"

        if self.dry_run:
            self._log(f"[DRY-RUN] Would move: {source.name} -> {destination.parent.name}/")
            return self._write_move_audit(
                {
                    "event": "file_move",
                    "timestamp": now_iso(),
                    "execute": False,
                    "src": str(source),
                    "dest": str(destination),
                    "result": "dry_run",
                    "verification": verification,
                }
            )

        if destination.exists() and not allow_overwrite:
            self.ui.error(f"Destination already exists, refusing to overwrite: {destination}")
            self._write_move_audit(
                {
                    "event": "file_move",
                    "timestamp": now_iso(),
                    "execute": True,
                    "src": str(source),
                    "dest": str(destination),
                    "result": "skip_dest_exists",
                    "verification": verification,
                }
            )
            return False

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            source_size = source.stat().st_size
            source_checksum = get_sha256(source) if verify_checksum else None

            temp_path = destination.with_name(f".{destination.name}.tmp")
            counter = 1
            while temp_path.exists():
                temp_path = destination.with_name(f".{destination.name}.tmp.{counter}")
                counter += 1

            self._copy_to_temp(
                source,
                temp_path,
                verify_checksum=verify_checksum,
                source_checksum=source_checksum,
            )

            os.replace(temp_path, destination)
            self._log(f"[MOVE] {source.name} -> {destination.parent.name}/{destination.name}")

            deleted = self.safe_delete(
                source,
                confirmation_phrase,
                skip_confirmation=skip_confirmation,
            )
            if not deleted:
                self._write_move_audit(
                    {
                        "event": "file_move",
                        "timestamp": now_iso(),
                        "execute": True,
                        "src": str(source),
                        "dest": str(destination),
                        "result": "error",
                        "verification": verification,
                        "error": "source_delete_failed_after_destination_write",
                    }
                )
                return False

            dest_size = destination.stat().st_size
            if dest_size != source_size:
                self._write_move_audit(
                    {
                        "event": "file_move",
                        "timestamp": now_iso(),
                        "execute": True,
                        "src": str(source),
                        "dest": str(destination),
                        "result": "error",
                        "verification": verification,
                        "source_size": source_size,
                        "dest_size": dest_size,
                        "error": f"size_mismatch: src={source_size} dest={dest_size}",
                    }
                )
                return False

            return self._write_move_audit(
                {
                    "event": "file_move",
                    "timestamp": now_iso(),
                    "execute": True,
                    "src": str(source),
                    "dest": str(destination),
                    "result": "moved",
                    "verification": verification,
                    "source_size": source_size,
                    "dest_size": dest_size,
                }
            )
        except (IOError, shutil.SameFileError, OSError) as e:
            self.ui.error(f"Failed to move or verify {source} to {destination}: {e}")
            try:
                if "temp_path" in locals() and temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            self._write_move_audit(
                {
                    "event": "file_move",
                    "timestamp": now_iso(),
                    "execute": True,
                    "src": str(source),
                    "dest": str(destination),
                    "result": "error",
                    "verification": verification,
                    "error": f"{type(e).__name__}: {e}",
                }
            )
            return False

    def safe_delete(
        self,
        path: Path,
        confirmation_phrase: str,
        skip_confirmation: bool = False,
    ) -> bool:
        """
        Safely deletes a file after asking for user confirmation.
        """
        if self.dry_run:
            self._log(f"[DRY-RUN] Would delete: {path.name}")
            return True

        if skip_confirmation or self.gates.confirm_destructive_operation(
            "file deletion",
            confirmation_phrase,
        ):
            try:
                path.unlink()
                self._log(f"[DELETE] {path.name}")
                return True
            except OSError as e:
                self.ui.error(f"Failed to delete {path}: {e}")
                return False
        else:
            self.ui.warning(f"Deletion of {path} cancelled by user.")
            return False
