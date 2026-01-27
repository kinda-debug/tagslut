from __future__ import annotations
import hashlib
import shutil
from pathlib import Path

from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.safety_gates import SafetyGates


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

    def __init__(self, ui: ConsoleUI, gates: SafetyGates, dry_run: bool = True, quiet: bool = False):
        self.ui = ui
        self.gates = gates
        self.dry_run = dry_run
        self.quiet = quiet  # Suppress per-file output (caller handles it)

    def _log(self, message: str):
        """Internal logging that respects quiet mode."""
        if not self.quiet:
            self.ui.print(message)

    def safe_copy(
        self,
        source: Path,
        destination: Path,
        verify_checksum: bool = True,
    ) -> bool:
        """
        Safely copies a file from source to destination.

        Args:
            source: The path to the source file.
            destination: The path to the destination file.
            verify_checksum: Whether to verify the checksum after copying.

        Returns:
            True if the operation was successful, False otherwise.
        """
        if self.dry_run:
            self._log(f"[DRY-RUN] Would copy: {source} -> {destination}")
            return True

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            self._log(f"[COPY] {source.name} -> {destination.parent.name}/{destination.name}")

            # Verify the copy
            if destination.stat().st_size != source.stat().st_size:
                raise IOError("Target file size does not match source.")

            if verify_checksum:
                source_checksum = get_sha256(source)
                dest_checksum = get_sha256(destination)
                if source_checksum != dest_checksum:
                    raise IOError(
                        f"Target checksum mismatch. Expected {source_checksum}, got {dest_checksum}"
                    )
            return True
        except (IOError, shutil.SameFileError) as e:
            self.ui.error(f"Failed to copy or verify {source} to {destination}: {e}")
            return False

    def safe_move(
        self,
        source: Path,
        destination: Path,
        verify_checksum: bool = True,
        confirmation_phrase: str = "I understand this is a move operation.",
        skip_confirmation: bool = False,
    ) -> bool:
        """
        Safely moves a file from source to destination.
        This is implemented as a safe_copy followed by a safe_delete.
        """
        if self.dry_run:
            self._log(f"[DRY-RUN] Would move: {source.name} -> {destination.parent.name}/")
            return True

        if self.safe_copy(source, destination, verify_checksum):
            return self.safe_delete(source, confirmation_phrase, skip_confirmation=skip_confirmation)
        return False

    def safe_delete(self, path: Path, confirmation_phrase: str, skip_confirmation: bool = False) -> bool:
        """
        Safely deletes a file after asking for user confirmation.
        """
        if self.dry_run:
            self._log(f"[DRY-RUN] Would delete: {path.name}")
            return True

        if skip_confirmation or self.gates.confirm_destructive_operation("file deletion", confirmation_phrase):
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
