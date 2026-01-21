from __future__ import annotations
import os
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[3]))

from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.safety_gates import SafetyGates
from dedupe.utils.file_operations import FileOperations


def undo_quarantine(quarantine_root: str, dry_run: bool):
    ui = ConsoleUI()
    gates = SafetyGates(ui)
    file_ops = FileOperations(ui, gates, dry_run=dry_run)

    q_root = Path(quarantine_root)
    if not q_root.exists():
        ui.error(f"Error: {quarantine_root} not found.")
        return

    ui.print(f"Restoring files from {q_root}...")

    success = 0
    errors = 0

    # Use os.walk to find all files in quarantine
    for root, _, files in os.walk(q_root):
        for name in files:
            src = Path(root) / name
            rel_path = src.relative_to(q_root)

            # Reconstruct original path.
            target_path = Path("/Volumes") / rel_path

            if file_ops.safe_move(src, target_path, confirmation_phrase=f"undo quarantine for {src}"):
                success += 1
            else:
                errors += 1
            
            if success % 100 == 0:
                ui.print(f"Restored {success} files...")

    ui.print(f"\nFinished: {success} restored, {errors} errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("quarantine_paths", nargs="+", help="Paths to quarantine folders to undo")
    parser.add_argument("--execute", action="store_true", help="Actually move files")
    args = parser.parse_args()

    for path in args.quarantine_paths:
        undo_quarantine(path, dry_run=not args.execute)
