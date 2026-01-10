#!/usr/bin/env python3
"""
Auto-mark duplicate decisions from a recommend plan.

Reads a recommend_plan.json and emits a CSV with KEEP/DROP suggestions per path,
using simple heuristics:
  - Prefer higher zone priority: accepted > staging > suspect > quarantine > other/None
  - Prefer integrity_state valid > recoverable > None > corrupt
  - Prefer flac_ok True over False/None
  - Prefer shorter paths as a final tiebreaker

This does NOT move or delete files. It only produces a suggestion CSV you can review.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ZonePriority = ["accepted", "staging", "suspect", "quarantine"]
IntegrityPriority = ["valid", "recoverable", None, "corrupt"]


@dataclass
class RankedDecision:
    group_id: str
    path: str
    library: str | None
    zone: str | None
    integrity_state: str | None
    flac_ok: bool | None
    conflict_label: str | None
    base_reason: str
    rank: tuple[int, int, int, int]


def _rank(decision: Mapping[str, Any]) -> RankedDecision:
    ev = decision.get("evidence", {}) or {}
    fd = decision.get("file_details", {}) or {}
    zone = decision.get("zone")
    integrity_state = fd.get("integrity_state")
    flac_ok_raw = fd.get("flac_ok")
    flac_ok = bool(flac_ok_raw) if flac_ok_raw is not None else None

    # Lower is better for rank components
    zone_score = ZonePriority.index(zone) if zone in ZonePriority else len(ZonePriority)
    integrity_score = IntegrityPriority.index(integrity_state) if integrity_state in IntegrityPriority else len(IntegrityPriority)
    flac_score = 0 if flac_ok else 1
    path_score = len(decision.get("path", ""))

    return RankedDecision(
        group_id="",  # filled by caller
        path=decision.get("path"),
        library=decision.get("library"),
        zone=zone,
        integrity_state=integrity_state,
        flac_ok=flac_ok,
        conflict_label=ev.get("conflict_label"),
        base_reason=decision.get("reason", "Duplicate detected; curator review recommended."),
        rank=(zone_score, integrity_score, flac_score, path_score),
    )


def auto_mark(plan: Sequence[Mapping[str, Any]], output_csv: Path) -> None:
    headers = [
        "group_id",
        "path",
        "library",
        "zone",
        "integrity_state",
        "flac_ok",
        "conflict_label",
        "action",
        "reason",
        "confidence",
    ]

    with output_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for group in plan:
            gid = group.get("group_id")
            decisions: Iterable[Mapping[str, Any]] = group.get("decisions", [])
            ranked = []
            for d in decisions:
                rd = _rank(d)
                rd.group_id = gid
                ranked.append((rd.rank, rd, d))

            if not ranked:
                continue

            ranked.sort(key=lambda x: x[0])
            best_rank, best_rd, best_raw = ranked[0]

            for _, rd, raw in ranked:
                if rd is best_rd:
                    action = "KEEP"
                    confidence = "HIGH"
                    reason = f"Keep best-ranked path; zone={rd.zone}, integrity={rd.integrity_state}, flac_ok={rd.flac_ok}"
                else:
                    action = "DROP"
                    confidence = "MEDIUM"
                    reason = f"Lower-ranked duplicate vs keeper in group {gid}"

                writer.writerow(
                    [
                        rd.group_id,
                        rd.path,
                        rd.library,
                        rd.zone,
                        rd.integrity_state,
                        rd.flac_ok,
                        rd.conflict_label,
                        action,
                        reason,
                        confidence,
                    ]
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-mark KEEP/DROP suggestions from a recommend plan.")
    parser.add_argument(
        "--plan",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan.json",
        help="Path to recommend_plan.json",
    )
    parser.add_argument(
        "--output",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_auto_mark.csv",
        help="Where to write the suggestion CSV",
    )
    args = parser.parse_args()

    plan_path = Path(args.plan).expanduser()
    out_path = Path(args.output).expanduser()

    data = json.load(plan_path.open())
    plan = data.get("plan", [])
    auto_mark(plan, out_path)
    print(f"Wrote suggestions to {out_path}")


if __name__ == "__main__":
    main()
