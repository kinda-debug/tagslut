#!/usr/bin/env python3
"""
Summarize and visualize deduplication plan.json into human-readable formats.

Usage:
    python tools/review/plan_summary.py plan.json
    python tools/review/plan_summary.py plan.json --output summary.csv --format csv
    python tools/review/plan_summary.py plan.json --format table
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Any


def load_plan(plan_path: str) -> dict[str, Any]:
    """Load plan.json"""
    with open(plan_path) as f:
        return json.load(f)


def extract_duplicate_groups(plan: dict) -> list[dict]:
    """Extract and enrich duplicate groups from plan"""
    groups = []
    for item in plan.get("plan", []):
        if not item or "decisions" not in item:  # Skip empty objects
            continue

        decisions = item.get("decisions", [])
        if not decisions or len(decisions) < 2:
            continue

        # First decision is KEEP, rest are DROP
        keeper = decisions[0]
        dupes = decisions[1:]

        keeper_path = keeper.get("path", "?")
        keeper_size = keeper.get("file_details", {}).get("size", 0)
        keeper_zone = keeper.get("zone", "unknown")
        keeper_action = keeper.get("action", "KEEP")

        # Only track if keeper is actually being kept
        if keeper_action != "KEEP":
            continue

        total_dup_size = sum(d.get("file_details", {}).get("size", 0) for d in dupes)
        group_size = keeper_size + total_dup_size

        groups.append({
            "group_id": item.get("group_id", "?"),
            "keeper_path": keeper_path,
            "keeper_zone": keeper_zone,
            "keeper_size_mb": keeper_size / (1024 * 1024),
            "num_duplicates": len(dupes),
            "total_dup_size_mb": total_dup_size / (1024 * 1024),
            "group_total_size_mb": group_size / (1024 * 1024),
            "duplicate_paths": [d.get("path", "?") for d in dupes],
        })

    return groups


def print_summary_stats(groups: list[dict]) -> None:
    """Print high-level statistics"""
    if not groups:
        print("No duplicate groups found in plan.")
        return

    total_groups = len(groups)
    total_dups = sum(g["num_duplicates"] for g in groups)
    total_wasted_mb = sum(g["total_dup_size_mb"] for g in groups)
    total_wasted_gb = total_wasted_mb / 1024

    # Top duplicates by wasted space
    top_5 = sorted(groups, key=lambda g: g["total_dup_size_mb"], reverse=True)[:5]

    print("=" * 70)
    print("DEDUPLICATION PLAN SUMMARY")
    print("=" * 70)
    print(f"\nDuplicate Groups:     {total_groups}")
    print(f"Total Duplicate Files: {total_dups}")
    print(f"Wasted Space (if kept): {total_wasted_gb:.2f} GB ({total_wasted_mb:.0f} MB)")
    print(f"Space to Reclaim:       {total_wasted_gb:.2f} GB\n")

    print("TOP 5 DUPLICATE GROUPS BY SIZE")
    print("-" * 70)
    for i, g in enumerate(top_5, 1):
        print(f"\n{i}. {g['keeper_path']}")
        print(f"   Keeper Zone: {g['keeper_zone']} ({g['keeper_size_mb']:.1f} MB)")
        print(f"   Duplicates:  {g['num_duplicates']} files ({g['total_dup_size_mb']:.1f} MB wasted)")
        print(f"   Total Group: {g['group_total_size_mb']:.1f} MB")


def write_csv(groups: list[dict], output_path: str) -> None:
    """Write detailed CSV report"""
    import csv

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "keeper_path",
            "keeper_zone",
            "keeper_size_mb",
            "num_duplicates",
            "total_dup_size_mb",
            "group_total_size_mb",
        ])
        writer.writeheader()

        for g in sorted(groups, key=lambda x: x["group_total_size_mb"], reverse=True):
            writer.writerow({
                "keeper_path": g["keeper_path"],
                "keeper_zone": g["keeper_zone"],
                "keeper_size_mb": f"{g['keeper_size_mb']:.1f}",
                "num_duplicates": g["num_duplicates"],
                "total_dup_size_mb": f"{g['total_dup_size_mb']:.1f}",
                "group_total_size_mb": f"{g['group_total_size_mb']:.1f}",
            })

    print(f"\n✓ CSV written to {output_path}")


def write_detailed_json(groups: list[dict], output_path: str) -> None:
    """Write detailed JSON with duplicate paths included"""
    with open(output_path, "w") as f:
        json.dump(groups, f, indent=2)

    print(f"✓ Detailed JSON written to {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python plan_summary.py plan.json [--output FILE] [--format csv|json|table]")
        sys.exit(1)

    plan_path = sys.argv[1]
    output_path = None
    fmt = "table"

    # Parse flags
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--output":
            output_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--format":
            fmt = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # Load and process
    plan = load_plan(plan_path)
    groups = extract_duplicate_groups(plan)

    # Print summary
    print_summary_stats(groups)

    # Write output
    if output_path:
        if fmt == "csv":
            write_csv(groups, output_path)
        elif fmt == "json":
            write_detailed_json(groups, output_path)
    else:
        # Default: suggest CSV output
        suggested_csv = Path(plan_path).stem + "_report.csv"
        print(f"\n💡 Tip: Generate CSV report with:")
        print(f"   python tools/review/plan_summary.py {plan_path} --output {suggested_csv} --format csv")


if __name__ == "__main__":
    main()
