#!/usr/bin/env python3
"""
Prepare review artifacts from an enriched recommend plan CSV.

Outputs:
- recommend_marked_suggestions.csv : best-per-group KEEP with DROP for others
- recommend_keep_valid.csv         : only KEEP rows where integrity_state=valid and flac_ok=True
- cross_volume_conflicts.csv       : groups spanning multiple top-level prefixes (e.g., bad vs recovery vs commune)

Heuristics:
- Zone priority: accepted > staging > suspect > quarantine > other/None
- Integrity priority: valid > recoverable > None > corrupt
- flac_ok True preferred over False/None
- Shorter path as last tiebreaker
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

ZONE_PRIORITY = ["accepted", "staging", "suspect", "quarantine"]
INTEGRITY_PRIORITY = ["valid", "recoverable", None, "corrupt"]


@dataclass
class Row:
    group_id: str
    path: str
    library: str | None
    zone: str | None
    integrity_state: str | None
    flac_ok: bool | None
    conflict_label: str | None
    reason: str
    confidence: str
    deltas: Dict[str, Any]
    raw: List[str]

    @property
    def top_prefix(self) -> str:
        parts = Path(self.path).parts
        if len(parts) >= 3:
            return "/".join(parts[:3])
        return self.path

    @property
    def rank(self) -> tuple[int, int, int, int]:
        zone_score = ZONE_PRIORITY.index(self.zone) if self.zone in ZONE_PRIORITY else len(ZONE_PRIORITY)
        integrity_score = (
            INTEGRITY_PRIORITY.index(self.integrity_state)
            if self.integrity_state in INTEGRITY_PRIORITY
            else len(INTEGRITY_PRIORITY)
        )
        flac_score = 0 if self.flac_ok else 1
        path_score = len(self.path or "")
        return (zone_score, integrity_score, flac_score, path_score)


def parse_row(header: Sequence[str], row: Sequence[str]) -> Row:
    data = dict(zip(header, row))
    flac_ok_raw = data.get("flac_ok")
    flac_ok: bool | None
    if flac_ok_raw in ("True", "true", "1"):
        flac_ok = True
    elif flac_ok_raw in ("False", "false", "0"):
        flac_ok = False
    else:
        flac_ok = None

    deltas = {
        "duration_diff": data.get("duration_diff") or 0,
        "bitrate_diff": data.get("bitrate_diff") or 0,
        "sample_rate_diff": data.get("sample_rate_diff") or 0,
        "bit_depth_diff": data.get("bit_depth_diff") or 0,
    }
    return Row(
        group_id=data.get("group_id", ""),
        path=data.get("path", ""),
        library=data.get("library"),
        zone=data.get("zone"),
        integrity_state=data.get("integrity_state"),
        flac_ok=flac_ok,
        conflict_label=data.get("conflict_label"),
        reason=data.get("reason", ""),
        confidence=data.get("confidence", ""),
        deltas=deltas,
        raw=list(row),
    )


def load_rows(path: Path) -> list[Row]:
    with path.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        return [parse_row(header, r) for r in reader if r]


def write_rows(path: Path, header: list[str], rows: Iterable[Sequence[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def best_per_group(rows: list[Row]) -> dict[str, Row]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(r.group_id, []).append(r)
    best: dict[str, Row] = {}
    for gid, entries in groups.items():
        entries.sort(key=lambda r: r.rank)
        best[gid] = entries[0]
    return best


def cross_volume_groups(rows: list[Row]) -> dict[str, list[Row]]:
    groups: dict[str, list[Row]] = {}
    for r in rows:
        groups.setdefault(r.group_id, []).append(r)
    out = {}
    for gid, entries in groups.items():
        prefixes = {e.top_prefix for e in entries}
        if len(prefixes) > 1:
            out[gid] = entries
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare filtered/suggested review artifacts from enriched plan CSV.")
    parser.add_argument(
        "--plan",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports/recommend_plan_enriched.csv",
        help="Path to enriched plan CSV (with zone/integrity/flac_ok)",
    )
    parser.add_argument(
        "--out-dir",
        default="/Users/georgeskhawam/Projects/dedupe/artifacts/M/03_reports",
        help="Directory to write derived CSVs",
    )
    args = parser.parse_args()

    plan_path = Path(args.plan).expanduser()
    out_dir = Path(args.out_dir).expanduser()

    rows = load_rows(plan_path)
    header = [
        "group_id",
        "path",
        "library",
        "zone",
        "action",
        "reason",
        "confidence",
        "conflict_label",
        "duration_diff",
        "bitrate_diff",
        "sample_rate_diff",
        "bit_depth_diff",
        "integrity_state",
        "flac_ok",
    ]

    # Best per group (KEEP/DROP suggestions)
    best = best_per_group(rows)
    suggestions: list[list[str]] = []
    keep_valid: list[list[str]] = []
    for r in rows:
        keeper = best[r.group_id]
        if r.path == keeper.path:
            action = "KEEP"
            reason = f"Best-ranked (zone={r.zone}, integrity={r.integrity_state}, flac_ok={r.flac_ok})"
            confidence = "HIGH"
        else:
            action = "DROP"
            reason = f"Lower-ranked vs keeper in group {r.group_id}"
            confidence = "MEDIUM"
        row_out = [
            r.group_id,
            r.path,
            r.library,
            r.zone,
            action,
            reason,
            confidence,
            r.conflict_label,
            r.deltas["duration_diff"],
            r.deltas["bitrate_diff"],
            r.deltas["sample_rate_diff"],
            r.deltas["bit_depth_diff"],
            r.integrity_state,
            r.flac_ok,
        ]
        suggestions.append(row_out)
        if action == "KEEP" and r.integrity_state == "valid" and r.flac_ok:
            keep_valid.append(row_out)

    write_rows(out_dir / "recommend_marked_suggestions.csv", header, suggestions)
    write_rows(out_dir / "recommend_keep_valid.csv", header, keep_valid)

    # Cross-volume conflicts
    cv = cross_volume_groups(rows)
    cv_rows: list[list[str]] = []
    for gid, entries in cv.items():
        entries.sort(key=lambda r: r.rank)
        keeper = entries[0]
        for r in entries:
            action = "KEEP" if r.path == keeper.path else "DROP"
            reason = f"Cross-volume; best-ranked is {keeper.top_prefix}"
            cv_rows.append(
                [
                    r.group_id,
                    r.path,
                    r.library,
                    r.zone,
                    action,
                    reason,
                    "HIGH" if action == "KEEP" else "MEDIUM",
                    r.conflict_label,
                    r.deltas["duration_diff"],
                    r.deltas["bitrate_diff"],
                    r.deltas["sample_rate_diff"],
                    r.deltas["bit_depth_diff"],
                    r.integrity_state,
                    r.flac_ok,
                ]
            )
    write_rows(out_dir / "cross_volume_conflicts.csv", header, cv_rows)

    print("Wrote:")
    print(" ", out_dir / "recommend_marked_suggestions.csv")
    print(" ", out_dir / "recommend_keep_valid.csv")
    print(" ", out_dir / "cross_volume_conflicts.csv")


if __name__ == "__main__":
    main()
