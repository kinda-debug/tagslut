"""
Generate a clean recovery manifest from matches.csv.
Ensures required columns:
    library_path
    recovered_path
"""

from __future__ import annotations
import csv
from pathlib import Path
import logging

LOGGER = logging.getLogger(__name__)


REQUIRED_COLUMNS = [
    "library_path",
    "recovered_path",
]

OUTPUT_COLUMNS = [
    "library_path",
    "recovered_path",
    "destination_name",
    "status",
    "confidence",
    "priority",
    "notes",
]


def generate_manifest(matches_csv: Path, out_csv: Path) -> None:
    matches_csv = Path(matches_csv)
    out_csv = Path(out_csv)

    LOGGER.info("Reading matches from %s", matches_csv)

    rows_out = []

    with matches_csv.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            lib = row.get("library_path")
            rec = row.get("recovered_path") or row.get("recovery_path")

            if not lib or not rec:
                continue

            rows_out.append({
                "library_path": lib,
                "recovered_path": rec,
                "destination_name": Path(lib).name,
                "status": "pending",
                "confidence": row.get("similarity", ""),
                "priority": "",
                "notes": "",
            })

    LOGGER.info("Writing manifest with %d rows to %s", len(rows_out), out_csv)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    LOGGER.info("Manifest generation complete.")