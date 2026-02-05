#!/usr/bin/env python3
"""
recommend_plan_to_moves.py

Convert `dedupe recommend` JSON output into an actionable MOVE plan CSV + path list.

Typical use:
  dedupe recommend --db "$DB" --mode checksum -o artifacts/plan_djssd_checksum.json
  python3 tools/review/recommend_plan_to_moves.py artifacts/plan_djssd_checksum.json \
    --out-csv artifacts/plan_djssd_checksum_moves.csv \
    --out-paths artifacts/plan_djssd_checksum_move_paths.txt

Then:
  python3 tools/review/dump_file_tags.py --paths-file artifacts/plan_djssd_checksum_move_paths.txt --out ...
  python3 tools/review/quarantine_from_plan.py artifacts/plan_djssd_checksum_moves.csv --library-root /Volumes/DJSSD --quarantine-root ... --execute

This script NEVER moves files; it only produces a plan.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _csv_path(p: Path) -> Path:
    p = p.expanduser()
    if not str(p).endswith(".csv"):
        return Path(str(p) + ".csv")
    return p


def _txt_path(p: Path) -> Path:
    p = p.expanduser()
    if not str(p).endswith(".txt"):
        return Path(str(p) + ".txt")
    return p


def _as_list(csv_value: Optional[str]) -> List[str]:
    if not csv_value:
        return []
    return [x.strip() for x in csv_value.split(",") if x.strip()]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Convert dedupe recommend JSON plan into MOVE CSV + paths file")
    ap.add_argument("plan_json", type=Path, help="Path to plan JSON produced by `dedupe recommend`")
    ap.add_argument("--out-csv", type=Path, default=Path("artifacts/recommend_moves.csv"), help="Output CSV path")
    ap.add_argument("--out-paths", type=Path, default=Path("artifacts/recommend_move_paths.txt"), help="Output paths file")
    ap.add_argument("--from-action", default="DROP", help="Decision action to convert into MOVE rows (default: DROP)")
    ap.add_argument(
        "--require-keeper-zone",
        default="accepted",
        help="Only emit MOVE rows when the group's keeper is in one of these zones (csv). Default: accepted",
    )
    ap.add_argument(
        "--move-zones",
        default="staging,suspect",
        help="Only emit MOVE rows for decisions in these zones (csv). Default: staging,suspect",
    )
    ap.add_argument(
        "--only-prefix",
        action="append",
        default=[],
        help="Only emit MOVE rows for paths starting with this prefix (repeatable).",
    )
    ap.add_argument(
        "--keeper-prefix",
        action="append",
        default=[],
        help="Only include groups whose KEEP path starts with this prefix (repeatable).",
    )
    ap.add_argument(
        "--move-prefix",
        action="append",
        default=[],
        help="Only emit MOVE rows whose path starts with this prefix (repeatable).",
    )
    ap.add_argument(
        "--skip-flag",
        action="append",
        default=[],
        help="Skip entire groups containing this flag (repeatable).",
    )
    return ap.parse_args()


def _find_keeper(decisions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for d in decisions:
        if (d.get("action") or "").upper() == "KEEP":
            return d
    return None


def main() -> int:
    args = parse_args()
    plan_path = args.plan_json.expanduser().resolve()
    out_csv = _csv_path(args.out_csv).expanduser().resolve()
    out_paths = _txt_path(args.out_paths).expanduser().resolve()

    from_action = (args.from_action or "").strip().upper()
    keeper_zones = {z.lower() for z in _as_list(args.require_keeper_zone)}
    move_zones = {z.lower() for z in _as_list(args.move_zones)}
    only_prefixes = [p for p in (args.only_prefix or []) if p]
    keeper_prefixes = [p for p in (args.keeper_prefix or []) if p]
    move_prefixes = [p for p in (args.move_prefix or []) if p]
    if only_prefixes:
        # Back-compat: --only-prefix applies to both keeper and move paths.
        keeper_prefixes = list(dict.fromkeys(only_prefixes + keeper_prefixes))
        move_prefixes = list(dict.fromkeys(only_prefixes + move_prefixes))
    skip_flags = {f for f in (args.skip_flag or []) if f}

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    match_mode = plan.get("match_mode")
    zone_priority = plan.get("zone_priority")

    rows_out: List[Dict[str, Any]] = []
    move_paths: List[str] = []

    for group in plan.get("plan", []) or []:
        group_id = group.get("group_id", "")
        group_flags = set(group.get("flags") or [])
        if skip_flags and group_flags.intersection(skip_flags):
            continue
        decisions = group.get("decisions") or []
        if not isinstance(decisions, list) or len(decisions) < 2:
            continue

        keeper = _find_keeper(decisions)
        if not keeper:
            continue

        keeper_zone = (keeper.get("zone") or "").lower()
        if keeper_zones and keeper_zone not in keeper_zones:
            continue

        keeper_path = keeper.get("path", "")
        if keeper_prefixes and keeper_path and not any(keeper_path.startswith(p) for p in keeper_prefixes):
            continue
        for d in decisions:
            action = (d.get("action") or "").upper()
            zone = (d.get("zone") or "").lower()
            path = d.get("path", "")
            if action != from_action:
                continue
            if move_zones and zone not in move_zones:
                continue
            if not path:
                continue
            if move_prefixes and not any(path.startswith(p) for p in move_prefixes):
                continue

            fd = d.get("file_details") or {}
            rows_out.append(
                {
                    "action": "MOVE",
                    "group": group_id,
                    "match_mode": match_mode,
                    "keeper_zone": keeper_zone,
                    "keeper_path": keeper_path,
                    "zone": zone,
                    "path": path,
                    "reason": d.get("reason", ""),
                    "confidence": d.get("confidence", ""),
                    "checksum": fd.get("checksum") or d.get("hash") or "",
                    "duration_s": fd.get("duration") or "",
                    "sample_rate": fd.get("sample_rate") or "",
                    "bit_depth": fd.get("bit_depth") or "",
                    "bitrate": fd.get("bitrate") or "",
                    "size": fd.get("size") or "",
                }
            )
            move_paths.append(path)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_paths.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "action",
        "group",
        "match_mode",
        "keeper_zone",
        "keeper_path",
        "zone",
        "path",
        "reason",
        "confidence",
        "checksum",
        "duration_s",
        "sample_rate",
        "bit_depth",
        "bitrate",
        "size",
    ]

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    out_paths.write_text("\n".join(move_paths) + ("\n" if move_paths else ""), encoding="utf-8")

    print(f"Plan: {plan_path}")
    print(f"match_mode={match_mode} zone_priority={zone_priority}")
    print(f"MOVE rows: {len(rows_out)}")
    print(f"Wrote: {out_csv}")
    print(f"Wrote: {out_paths}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
