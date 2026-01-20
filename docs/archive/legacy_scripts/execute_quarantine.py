from __future__ import annotations
import csv
import os
import shutil
from pathlib import Path
import datetime

def main():
    plan_file = "equal_treatment_dedupe_plan.csv"
    if not os.path.exists(plan_file):
        print(f"Error: {plan_file} not found. Run generate_equal_plan.py first.")
        return

    # Define quarantine root
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    quarantine_root = Path(f"/Volumes/COMMUNE/M/_quarantine/DEDUPE_{timestamp}")

    print(f"Quarantine location: {quarantine_root}")

    # Read the plan
    moves = []
    with open(plan_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            moves.append(row)

    print(f"Found {len(moves)} moves in plan.")

    # Check if we should actually run
    confirm = os.environ.get("CONFIRM_MOVE", "false").lower() == "true"

    if not confirm:
        print("\n*** DRY RUN MODE ***")
        print("To actually move files, run with environment variable CONFIRM_MOVE=true")
        print("Example: CONFIRM_MOVE=true python3 execute_quarantine.py")
    else:
        print("\n*** EXECUTION MODE ***")
        if not quarantine_root.exists():
            quarantine_root.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, move in enumerate(moves):
        src = Path(move['path'])

        # Determine relative path for quarantine to preserve some structure
        # We'll use the volume name + the path
        if src.parts[1] == 'Volumes':
            rel_path = Path(*src.parts[2:])
        else:
            rel_path = src.relative_to('/')

        dest = quarantine_root / rel_path

        if not src.exists():
            print(f"[{i+1}/{len(moves)}] SKIP: Source does not exist: {src}")
            skip_count += 1
            continue

        if confirm:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                success_count += 1
                if success_count % 100 == 0:
                    print(f"[{i+1}/{len(moves)}] Moved {success_count} files...")
            except Exception as e:
                print(f"[{i+1}/{len(moves)}] ERROR moving {src}: {e}")
                fail_count += 1
        else:
            # Dry run: just check existence
            success_count += 1
            if success_count % 1000 == 0:
                print(f"[{i+1}/{len(moves)}] Validated {success_count} files exist...")

    print("\n--- Final Status ---")
    if confirm:
        print(f"Successfully moved: {success_count}")
        print(f"Failed to move: {fail_count}")
        print(f"Skipped (missing): {skip_count}")
    else:
        print(f"Files validated for move: {success_count}")
        print(f"Files missing: {skip_count}")
        print("\nNo files were moved. Run with CONFIRM_MOVE=true to execute.")

if __name__ == "__main__":
    main()
