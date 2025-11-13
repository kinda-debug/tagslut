#!/usr/bin/env python3
"""Verify NEW_LIBRARY contains all files from the move plan.

Reads artifacts/reports/library_move_plan.csv and checks os.path.exists
for each destination. Writes a JSONL report and prints a concise summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Dict, List


def verify(
    plan_csv: Path,
    out_jsonl: Path,
    missing_out: Path,
    progress_every: int = 500,
) -> Dict[str, int]:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    missing_out.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    present = 0
    missing = 0

    per_source: Dict[str, Dict[str, int]] = {}

    with (
        plan_csv.open("r", newline="") as f,
        out_jsonl.open("w") as jout,
        missing_out.open("w") as mout,
    ):
        reader = csv.DictReader(f)
        rows: List[Dict[str, str]] = list(reader)
        total = len(rows)

        for i, row in enumerate(rows, 1):
            dest = row["destination"]
            src_root = row.get("source_root", "?")
            exists = os.path.exists(dest)

            stat = {
                "md5": row.get("md5"),
                "destination": dest,
                "exists": exists,
                "source_root": src_root,
            }
            jout.write(json.dumps(stat) + "\n")

            bucket = per_source.setdefault(
                src_root, {"present": 0, "missing": 0}
            )
            if exists:
                present += 1
                bucket["present"] += 1
            else:
                missing += 1
                bucket["missing"] += 1
                mout.write(dest + "\n")

            if i % progress_every == 0:
                print(f"[{i:5d}/{total}] present={present} missing={missing}")

    print("\n=== NEW_LIBRARY Verification Summary ===")
    print(f"Plan files: {total}")
    print(f"Present:    {present}")
    print(f"Missing:    {missing}")
    for src_root in sorted(per_source):
        ps = per_source[src_root]
        print(
            f" - {src_root}: present={ps['present']} missing={ps['missing']}"
        )

    return {"total": total, "present": present, "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify NEW_LIBRARY against move plan"
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=Path("artifacts/reports/library_move_plan.csv"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/reports/new_library_verification.jsonl"),
    )
    ap.add_argument(
        "--missing-out",
        type=Path,
        default=Path("artifacts/reports/new_library_missing.txt"),
    )
    ap.add_argument("--progress-every", type=int, default=500)
    ns = ap.parse_args()

    if not ns.plan.exists():
        print(f"Plan CSV not found: {ns.plan}")
        return 1

    res = verify(ns.plan, ns.out, ns.missing_out, ns.progress_every)
    return 0 if res.get("missing", 1) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
