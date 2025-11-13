"""Generate recovery manifests from matcher output."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ManifestRow:
    """Structured row written to the manifest CSV."""

    library_path: str
    recovery_path: str
    destination_name: str
    status: str
    confidence: float
    priority: str
    notes: str


def _priority_for(status: str, confidence: float) -> str:
    if status in {"missing", "truncated"}:
        return "critical"
    if status == "exact" and confidence >= 0.85:
        return "high"
    if status == "potential_upgrade":
        return "high" if confidence >= 0.7 else "medium"
    if status == "orphan":
        return "low"
    return "review"


def _notes_for(status: str) -> str:
    if status == "truncated":
        return (
            "Recovered file appears shorter than library copy."
        )
    if status == "potential_upgrade":
        return (
            "Recovered file larger than library copy; inspect quality."
        )
    if status == "orphan":
        return (
            "No matching library entry; determine target manually."
        )
    if status == "missing":
        return "Library item has no recovery candidate."
    return ""


def _rows_from_matches(matches_csv: Path) -> Iterator[ManifestRow]:
    with matches_csv.open("r", encoding="utf8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = row.get("classification", "review")
            confidence = float(row.get("score") or 0.0)
            library_path = row.get("library_path", "")
            recovery_path = row.get("recovery_path", "")
            destination_name = Path(
                library_path or row.get("recovery_name", "")
            ).name
            priority = _priority_for(status, confidence)
            notes = _notes_for(status)
            yield ManifestRow(
                library_path=library_path,
                recovery_path=recovery_path,
                destination_name=destination_name,
                status=status,
                confidence=confidence,
                priority=priority,
                notes=notes,
            )


def generate_manifest(
    matches_csv: Path,
    output_csv: Path,
) -> list[ManifestRow]:
    """Create a recovery manifest and write it to *output_csv*."""

    rows = list(_rows_from_matches(matches_csv))
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "library_path",
                "recovery_path",
                "destination_name",
                "status",
                "confidence",
                "priority",
                "notes",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "library_path": row.library_path,
                    "recovery_path": row.recovery_path,
                    "destination_name": row.destination_name,
                    "status": row.status,
                    "confidence": f"{row.confidence:.3f}",
                    "priority": row.priority,
                    "notes": row.notes,
                }
            )
    LOGGER.info("Wrote manifest with %s rows to %s", len(rows), output_csv)
    return rows
