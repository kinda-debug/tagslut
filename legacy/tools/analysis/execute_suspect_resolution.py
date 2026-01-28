from __future__ import annotations
import os
import pandas as pd
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.utils.console_ui import ConsoleUI
from dedupe.utils.safety_gates import SafetyGates
from dedupe.utils.file_operations import FileOperations


def execute_resolution(report_csv: str, dry_run: bool = True):
    if not os.path.exists(report_csv):
        print(f"Error: {report_csv} not found")
        return

    df = pd.read_csv(report_csv)
    ui = ConsoleUI()
    gates = SafetyGates(ui)
    file_ops = FileOperations(ui, gates, dry_run=dry_run)

    ui.print(f"Executing resolution from {report_csv}")
    ui.print(f"Dry run: {dry_run}")

    counts = {"PROMOTE": 0, "QUARANTINE": 0, "DELETE": 0, "SKIP": 0, "ERROR": 0}

    library_root = Path("/Volumes/COMMUNE/M/Library")
    quarantine_root = Path("/Volumes/COMMUNE/M/_quarantine/suspect_duplicates")
    suspect_root = Path("/Volumes/COMMUNE/M/Suspect")

    for _, row in df.iterrows():
        path = Path(row["path"])
        action = row["action"]

        if not path.exists():
            ui.warning(f"File not found, skipping: {path}")
            counts["SKIP"] += 1
            continue

        try:
            if action == "DELETE":
                if file_ops.safe_delete(path, "delete suspect file"):
                    counts["DELETE"] += 1
                else:
                    counts["ERROR"] += 1

            elif action == "QUARANTINE":
                rel_path = path.relative_to(suspect_root)
                dest = quarantine_root / rel_path
                if file_ops.safe_move(path, dest, confirmation_phrase="quarantine suspect file"):
                    counts["QUARANTINE"] += 1
                else:
                    counts["ERROR"] += 1

            elif action == "PROMOTE":
                rel_path = path.relative_to(suspect_root)
                dest = library_root / rel_path
                if file_ops.safe_move(path, dest, confirmation_phrase="promote suspect file"):
                    counts["PROMOTE"] += 1
                else:
                    counts["ERROR"] += 1
            else:
                counts["SKIP"] += 1
        except Exception as e:
            ui.error(f"Error processing {path}: {e}")
            counts["ERROR"] += 1

    ui.print("\nExecution Summary:")
    for k, v in counts.items():
        ui.print(f"{k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="suspect_resolution_report.csv")
    parser.add_argument("--execute", action="store_true", help="Actually move/delete files")
    args = parser.parse_args()

    execute_resolution(args.report, dry_run=not args.execute)
