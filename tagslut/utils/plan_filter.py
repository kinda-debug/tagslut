"""
Plan Filter Module

Consolidated utilities for filtering and marking deduplication plans.
Combines functionality from auto_mark.py and prepare_enriched.py.

Features:
- Rank files within duplicate groups
- Auto-mark KEEP/DROP decisions
- Filter for valid files
- Identify cross-volume conflicts
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from tagslut.utils.zones import coerce_zone, zone_priority, DEFAULT_PATH_PRIORITY

# Priority lists (lower index = higher priority)
INTEGRITY_PRIORITY = ["valid", "recoverable", None, "corrupt"]


@dataclass
class RankedFile:
    """A file with ranking information for decision-making."""

    group_id: str
    path: str
    library: Optional[str] = None
    zone: Optional[str] = None
    integrity_state: Optional[str] = None
    flac_ok: Optional[bool] = None
    conflict_label: Optional[str] = None
    reason: str = ""
    confidence: str = ""
    deltas: Dict[str, Any] = field(default_factory=dict)

    @property
    def top_prefix(self) -> str:
        """Get the top-level path prefix (e.g., /Volumes/NAME)."""
        parts = Path(self.path).parts
        if len(parts) >= 3:
            return "/".join(parts[:3])
        return self.path

    @property
    def rank(self) -> tuple[int, int, int, int]:
        """
        Compute ranking tuple (lower is better).

        Order: zone_priority, integrity_priority, flac_ok, path_length
        """
        zone_value = coerce_zone(self.zone)
        zone_score = zone_priority(zone_value) if zone_value else DEFAULT_PATH_PRIORITY
        integrity_score = (
            INTEGRITY_PRIORITY.index(self.integrity_state)
            if self.integrity_state in INTEGRITY_PRIORITY
            else len(INTEGRITY_PRIORITY)
        )
        flac_score = 0 if self.flac_ok else 1
        path_score = len(self.path or "")
        return (zone_score, integrity_score, flac_score, path_score)


def rank_file(decision: Mapping[str, Any], group_id: str = "") -> RankedFile:
    """
    Create a RankedFile from a decision dict.

    Args:
        decision: Dict with path, zone, file_details, evidence, etc.
        group_id: The duplicate group ID

    Returns:
        RankedFile with computed rank
    """
    ev = decision.get("evidence", {}) or {}
    fd = decision.get("file_details", {}) or {}
    zone = decision.get("zone")
    integrity_state = fd.get("integrity_state")
    flac_ok_raw = fd.get("flac_ok")
    flac_ok = bool(flac_ok_raw) if flac_ok_raw is not None else None

    return RankedFile(
        group_id=group_id,
        path=decision.get("path", ""),
        library=decision.get("library"),
        zone=zone,
        integrity_state=integrity_state,
        flac_ok=flac_ok,
        conflict_label=ev.get("conflict_label"),
        reason=decision.get("reason", "Duplicate detected; curator review recommended."),
    )


def parse_csv_row(header: Sequence[str], row: Sequence[str]) -> RankedFile:
    """Parse a CSV row into a RankedFile."""
    data = dict(zip(header, row))

    flac_ok_raw = data.get("flac_ok")
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

    return RankedFile(
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
    )


def best_per_group(files: List[RankedFile]) -> Dict[str, RankedFile]:
    """
    Find the best-ranked file in each group.

    Args:
        files: List of RankedFile objects

    Returns:
        Dict mapping group_id to best RankedFile
    """
    groups: Dict[str, List[RankedFile]] = {}
    for f in files:
        groups.setdefault(f.group_id, []).append(f)

    best: Dict[str, RankedFile] = {}
    for gid, entries in groups.items():
        entries.sort(key=lambda r: r.rank)
        best[gid] = entries[0]
    return best


def find_cross_volume_conflicts(files: List[RankedFile]) -> Dict[str, List[RankedFile]]:
    """
    Find groups that span multiple top-level volumes.

    Args:
        files: List of RankedFile objects

    Returns:
        Dict mapping group_id to list of files for cross-volume groups
    """
    groups: Dict[str, List[RankedFile]] = {}
    for f in files:
        groups.setdefault(f.group_id, []).append(f)

    conflicts = {}
    for gid, entries in groups.items():
        prefixes = {e.top_prefix for e in entries}
        if len(prefixes) > 1:
            conflicts[gid] = entries
    return conflicts


def auto_mark_plan(
    plan: Sequence[Mapping[str, Any]],
    output_csv: Path,
) -> int:
    """
    Auto-mark KEEP/DROP suggestions from a recommend plan JSON.

    Args:
        plan: List of group dicts from recommend_plan.json
        output_csv: Path to write suggestion CSV

    Returns:
        Number of rows written
    """
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

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    rows_written = 0
    with output_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for group in plan:
            gid = group.get("group_id", "")
            decisions = group.get("decisions", [])

            ranked = []
            for d in decisions:
                rf = rank_file(d, gid)
                ranked.append(rf)

            if not ranked:
                continue

            ranked.sort(key=lambda r: r.rank)
            best = ranked[0]

            for rf in ranked:
                if rf.path == best.path:
                    action = "KEEP"
                    confidence = "HIGH"
                    reason = f"Keep best-ranked path; zone={rf.zone}, integrity={rf.integrity_state}, flac_ok={rf.flac_ok}"
                else:
                    action = "DROP"
                    confidence = "MEDIUM"
                    reason = f"Lower-ranked duplicate vs keeper in group {gid}"

                writer.writerow([
                    rf.group_id,
                    rf.path,
                    rf.library,
                    rf.zone,
                    rf.integrity_state,
                    rf.flac_ok,
                    rf.conflict_label,
                    action,
                    reason,
                    confidence,
                ])
                rows_written += 1

    return rows_written


def filter_enriched_plan(
    input_csv: Path,
    output_dir: Path,
) -> Dict[str, int]:
    """
    Filter enriched plan CSV and generate review artifacts.

    Outputs:
    - recommend_marked_suggestions.csv: KEEP/DROP for all files
    - recommend_keep_valid.csv: Only KEEP rows with valid integrity
    - cross_volume_conflicts.csv: Groups spanning multiple volumes

    Args:
        input_csv: Path to enriched plan CSV
        output_dir: Directory for output files

    Returns:
        Dict with counts for each output file
    """
    input_csv = Path(input_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load rows
    files: List[RankedFile] = []
    with input_csv.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            if row:
                files.append(parse_csv_row(header, row))

    # Find best per group
    best = best_per_group(files)

    # Output header
    out_header = [
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

    suggestions: List[List[Any]] = []
    keep_valid: List[List[Any]] = []

    for rf in files:
        keeper = best[rf.group_id]
        if rf.path == keeper.path:
            action = "KEEP"
            reason = f"Best-ranked (zone={rf.zone}, integrity={rf.integrity_state}, flac_ok={rf.flac_ok})"
            confidence = "HIGH"
        else:
            action = "DROP"
            reason = f"Lower-ranked vs keeper in group {rf.group_id}"
            confidence = "MEDIUM"

        row_out = [
            rf.group_id,
            rf.path,
            rf.library,
            rf.zone,
            action,
            reason,
            confidence,
            rf.conflict_label,
            rf.deltas.get("duration_diff", 0),
            rf.deltas.get("bitrate_diff", 0),
            rf.deltas.get("sample_rate_diff", 0),
            rf.deltas.get("bit_depth_diff", 0),
            rf.integrity_state,
            rf.flac_ok,
        ]
        suggestions.append(row_out)

        if action == "KEEP" and rf.integrity_state == "valid" and rf.flac_ok:
            keep_valid.append(row_out)

    # Write suggestions
    _write_csv(output_dir / "recommend_marked_suggestions.csv", out_header, suggestions)
    _write_csv(output_dir / "recommend_keep_valid.csv", out_header, keep_valid)

    # Cross-volume conflicts
    cv = find_cross_volume_conflicts(files)
    cv_rows: List[List[Any]] = []
    for gid, entries in cv.items():
        entries.sort(key=lambda r: r.rank)
        keeper = entries[0]
        for rf in entries:
            action = "KEEP" if rf.path == keeper.path else "DROP"
            reason = f"Cross-volume; best-ranked is {keeper.top_prefix}"
            cv_rows.append([
                rf.group_id,
                rf.path,
                rf.library,
                rf.zone,
                action,
                reason,
                "HIGH" if action == "KEEP" else "MEDIUM",
                rf.conflict_label,
                rf.deltas.get("duration_diff", 0),
                rf.deltas.get("bitrate_diff", 0),
                rf.deltas.get("sample_rate_diff", 0),
                rf.deltas.get("bit_depth_diff", 0),
                rf.integrity_state,
                rf.flac_ok,
            ])
    _write_csv(output_dir / "cross_volume_conflicts.csv", out_header, cv_rows)

    return {
        "suggestions": len(suggestions),
        "keep_valid": len(keep_valid),
        "cross_volume": len(cv_rows),
    }


def _write_csv(path: Path, header: List[str], rows: Iterable[Sequence[Any]]) -> None:
    """Write rows to a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
