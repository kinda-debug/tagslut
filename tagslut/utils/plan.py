"""
Utilities for handling removal plans.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlanRow:
    plan_id: str
    tier: str
    action: str
    reason: str
    sha256: str
    path: str
    source_zone: str
    keeper_path: str


def load_plan_rows(plan_path: Path) -> list[PlanRow]:
    rows: list[PlanRow] = []
    with plan_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = (row.get("action") or "").strip().upper()
            if action != "QUARANTINE":
                continue
            rows.append(
                PlanRow(
                    plan_id=row.get("plan_id", ""),
                    tier=row.get("tier", ""),
                    action=action,
                    reason=row.get("reason", ""),
                    sha256=row.get("sha256", ""),
                    path=row.get("path", ""),
                    source_zone=row.get("source_zone", ""),
                    keeper_path=row.get("keeper_path", ""),
                )
            )
    return rows
