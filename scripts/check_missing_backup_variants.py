#!/usr/bin/env python3
"""Analyze missing backup MD5s for potential variants in NEW_LIBRARY.

Uses move plan to index NEW_LIBRARY destinations by basename. For each
missing backup file (from garbage_backup_missing.tsv), checks if a file with
the same basename exists in NEW_LIBRARY (indicating an alternate encode/rip).

Outputs JSONL analysis and a restore plan TSV for those with no name match.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def load_move_plan(plan_csv: Path) -> List[Dict[str, str]]:
    with plan_csv.open("r", newline="") as f:
        return list(csv.DictReader(f))


def build_basename_index(
    plan_rows: List[Dict[str, str]]
) -> Dict[str, List[str]]:
    idx: Dict[str, List[str]] = {}
    for row in plan_rows:
        dest = row.get("destination") or ""
        base = Path(dest).name
        idx.setdefault(base, []).append(dest)
    return idx


def analyze(
    missing_tsv: Path,
    plan_csv: Path,
    out_jsonl: Path,
    restore_tsv: Path,
) -> Dict[str, int]:
    rows = load_move_plan(plan_csv)
    idx = build_basename_index(rows)

    total = 0
    name_match = 0
    no_match = 0

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    restore_tsv.parent.mkdir(parents=True, exist_ok=True)

    with (
        missing_tsv.open("r") as f,
        out_jsonl.open("w") as jout,
        restore_tsv.open("w") as rout,
    ):
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            md5, path_str = line.split("\t", 1)
            base = Path(path_str).name
            candidates = idx.get(base, [])
            if candidates:
                name_match += 1
            else:
                no_match += 1
                # Prepare restore entry: backup path -> proposed destination
                # Keep under NEW_LIBRARY/Garbage_backup/ preserving relative
                # structure after backup root
                rel = Path(path_str).parts
                # Find index of "Garbage copy" to preserve subpath after it
                try:
                    gc_idx = rel.index("Garbage copy")
                    sub = Path(*rel[gc_idx + 1:])
                except ValueError:
                    sub = Path(Path(path_str).name)
                dest = Path("/Volumes/dotad/NEW_LIBRARY/Garbage_backup") / sub
                rout.write(f"{path_str}\t{dest}\n")

            jout.write(
                json.dumps(
                    {
                        "md5": md5,
                        "backup_path": path_str,
                        "basename": base,
                        "name_match_in_new": bool(candidates),
                        "matched_paths": candidates,
                    }
                )
                + "\n"
            )

    print("\n=== Missing backup analysis ===")
    print(f"Missing from NEW_LIBRARY by MD5: {total}")
    print(f"With name-matched variants present: {name_match}")
    print(f"With no name match (candidate restore): {no_match}")

    return {"total": total, "name_match": name_match, "no_match": no_match}


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze missing backup variants")
    ap.add_argument(
        "--missing-tsv",
        type=Path,
        default=Path("artifacts/reports/garbage_backup_missing.tsv"),
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=Path("artifacts/reports/library_move_plan.csv"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(
            "artifacts/reports/garbage_backup_missing_analysis.jsonl"
        ),
    )
    ap.add_argument(
        "--restore-plan",
        type=Path,
        default=Path("artifacts/reports/garbage_backup_restore_plan.tsv"),
    )
    ns = ap.parse_args()

    if not ns.missing_tsv.exists():
        print(f"Missing TSV not found: {ns.missing_tsv}")
        return 1
    if not ns.plan.exists():
        print(f"Plan CSV not found: {ns.plan}")
        return 1

    _ = analyze(ns.missing_tsv, ns.plan, ns.out, ns.restore_plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
