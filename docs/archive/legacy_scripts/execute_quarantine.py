from __future__ import annotations
import csv
import os
import argparse
from pathlib import Path
import datetime
import sys

sys.path.insert(0, str(Path(__file__).parents[3]))

from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.safety_gates import SafetyGates
from dedupe.utils.file_operations import FileOperations

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("plan_file", help="Path to the plan CSV file")
    parser.add_argument("--execute", action="store_true", help="Actually move files")
    args = parser.parse_args()

    ui = ConsoleUI()
    gates = SafetyGates(ui)
    file_ops = FileOperations(ui, gates, dry_run=not args.execute)

    if not os.path.exists(args.plan_file):
        ui.error(f"Error: {args.plan_file} not found.")
        return

    # Define quarantine root
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_root = Path(f"/Volumes/COMMUNE/M/_quarantine/DEDUPE_{timestamp}")

    ui.print(f"Quarantine location: {quarantine_root}")

    # Read the plan
    moves = []
    with open(args.plan_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            moves.append(row)

    ui.print(f"Found {len(moves)} moves in plan.")

    if not args.execute:
        ui.print("\n*** DRY RUN MODE ***")
        ui.print("To actually move files, run with --execute")
    else:
        ui.print("\n*** EXECUTION MODE ***")
        if not quarantine_root.exists():
            quarantine_root.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, move in enumerate(moves):
        src = Path(move['path'])

        # Determine relative path for quarantine to preserve some structure
        if src.parts[1] == 'Volumes':
            rel_path = Path(*src.parts[2:])
        else:
            rel_path = src.relative_to('/')

        dest = quarantine_root / rel_path

        if not src.exists():
            ui.warning(f"[{i+1}/{len(moves)}] SKIP: Source does not exist: {src}")
            skip_count += 1
            continue

        if file_ops.safe_move(src, dest, confirmation_phrase=f"quarantine {src}"):
            success_count += 1
        else:
            fail_count += 1

        if success_count % 100 == 0:
            ui.print(f"[{i+1}/{len(moves)}] Moved {success_count} files...")

    ui.print("\n--- Final Status ---")
    if args.execute:
        ui.print(f"Successfully moved: {success_count}")
        ui.print(f"Failed to move: {fail_count}")
        ui.print(f"Skipped (missing): {skip_count}")
    else:
        ui.print(f"Files validated for move: {success_count}")
        ui.print(f"Files missing: {skip_count}")
        ui.print("\nNo files were moved. Run with --execute to execute.")

if __name__ == "__main__":
    main()
