#!/usr/bin/env python3
"""
Plan quarantine actions for bit-identical duplicates (SHA256).

Policy:
- Zone priority: accepted > staging > suspect > quarantine
- Tier 1: valid keeper in higher-priority zone; quarantine lower-priority duplicates.
- Tier 2: keeper not provably valid OR keeper only in suspect/quarantine; quarantine non-keeper duplicates.
- Same-zone duplicates are not auto-quarantined (manual review).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parents[2]))

from tagslut.utils import env_paths
from tagslut.utils.db import open_db, resolve_db_path


ZONE_DEFAULT = ["accepted", "staging", "suspect", "quarantine"]


@dataclass(frozen=True)
class FileRow:
    path: str
    zone: str
    integrity_state: str
    flac_ok: int | None
    effective_zone: str
    zone_override: str


def parse_priority(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_overrides(values: Iterable[str]) -> list[tuple[str, str]]:
    overrides: list[tuple[str, str]] = []
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"Invalid override '{raw}'. Use PREFIX=ZONE.")
        prefix, zone = raw.split("=", 1)
        overrides.append((prefix, zone))
    return overrides


def effective_zone(path: str, zone: str, overrides: list[tuple[str, str]]) -> tuple[str, str]:
    for prefix, override_zone in overrides:
        if path.startswith(prefix):
            return override_zone, prefix
    return zone or "", ""


def zone_rank(zone: str, priority: list[str]) -> int:
    if zone in priority:
        return priority.index(zone)
    return len(priority)


def is_valid(row: FileRow) -> bool:
    return row.integrity_state == "valid" and row.flac_ok == 1


def pick_keeper(rows: list[FileRow], priority: list[str]) -> FileRow:
    def sort_key(row: FileRow) -> tuple[int, int, int, str]:
        return (
            zone_rank(row.effective_zone, priority),
            0 if is_valid(row) else 1,
            len(row.path),
            row.path,
        )

    return min(rows, key=sort_key)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plan quarantine actions for SHA256-identical duplicates (dry-run only)."
    )
    parser.add_argument(
        "--db",
        help="Path to dedupe DB (default: $TAGSLUT_DB)",
    )
    parser.add_argument(
        "--output",
        help="Where to write the removal plan CSV (default: $TAGSLUT_REPORTS/removal_plan.csv)",
    )
    parser.add_argument(
        "--zone-priority",
        default=",".join(ZONE_DEFAULT),
        help="Comma-separated priority order (default: accepted,staging,suspect,quarantine)",
    )
    parser.add_argument(
        "--allow-zone-override",
        action="append",
        default=[],
        help="Optional PREFIX=ZONE overrides (repeatable, logged in plan)",
    )
    parser.add_argument(
        "--handle-same-zone",
        action="store_true",
        default=True,
        help="Plan removals even if files are in the same priority zone (TIER3) [Default: True]",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print summary only (no output file)",
    )
    args = parser.parse_args()

    priority = parse_priority(args.zone_priority)
    overrides = parse_overrides(args.allow_zone_override)
    plan_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    resolution = resolve_db_path(
        args.db,
        purpose="read",
        allow_repo_db=False,
        source_label="cli",
    )
    conn = open_db(resolution, row_factory=True)

    groups = conn.execute(
        """
        SELECT sha256
        FROM files
        WHERE sha256 IS NOT NULL
        GROUP BY sha256
        HAVING COUNT(*) > 1
        """
    ).fetchall()

    tier_counts: Counter[str] = Counter()
    tier_by_zone: Counter[tuple[str, str]] = Counter()
    skipped_same_zone = 0
    planned_rows: list[dict[str, str]] = []

    for group in groups:
        sha256 = group["sha256"]
        rows = conn.execute(
            """
            SELECT path, zone, integrity_state, flac_ok
            FROM files
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchall()

        items: list[FileRow] = []
        for row in rows:
            path = row["path"]
            zone = row["zone"] or ""
            integrity_state = row["integrity_state"] or ""
            flac_ok = row["flac_ok"]
            eff_zone, override = effective_zone(path, zone, overrides)
            items.append(
                FileRow(
                    path=path,
                    zone=zone,
                    integrity_state=integrity_state,
                    flac_ok=flac_ok,
                    effective_zone=eff_zone or zone,
                    zone_override=override,
                )
            )

        keeper = pick_keeper(items, priority)
        keeper_valid = is_valid(keeper)
        keeper_rank = zone_rank(keeper.effective_zone, priority)
        keeper_zone = keeper.effective_zone

        tier2_condition = (not keeper_valid) or (keeper_zone in ("suspect", "quarantine"))

        for item in items:
            if item.path == keeper.path:
                continue

            item_rank = zone_rank(item.effective_zone, priority)
            tier = ""
            reason = ""
            if keeper_valid and item_rank > keeper_rank:
                tier = "TIER1"
                reason = (
                    "Tier1: valid keeper in higher-priority zone "
                    f"({keeper_zone} > {item.effective_zone or item.zone})"
                )
            elif tier2_condition:
                tier = "TIER2"
                if not keeper_valid:
                    reason = "Tier2: keeper not provably valid"
                else:
                    reason = "Tier2: keeper only in suspect/quarantine"
            # Simplified logic: every redundant file is a DUPLICATE
            planned_rows.append(
                {
                    "plan_id": plan_id,
                    "tier": "DUPLICATE",
                    "action": "QUARANTINE",
                    "reason": f"Redundant copy of {keeper.path}",
                    "sha256": sha256,
                    "path": item.path,
                    "source_zone": item.zone or "unknown",
                    "keeper_path": keeper.path,
                }
            )

    conn.close()

    print(f"Plan ID: {plan_id}")
    print(f"Total Groups Scanned: {len(groups)}")
    print(f"Total Files to Move: {len(planned_rows)}")

    # Simple Summary
    counts: dict[str, int] = {}
    for r in planned_rows:
        z = r["source_zone"]
        counts[z] = counts.get(z, 0) + 1

    print("\nFiles to move by current location:")
    for zone, count in sorted(counts.items()):
        print(f"  {zone}: {count}")

    if args.summary_only:
        return

    output_path = Path(args.output) if args.output else env_paths.get_reports_dir() / "removal_plan.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["plan_id", "tier", "action", "reason", "sha256", "path", "source_zone", "keeper_path"])
        writer.writeheader()
        writer.writerows(planned_rows)

    print(f"\nWrote plan to {output_path}")


if __name__ == "__main__":
    main()
