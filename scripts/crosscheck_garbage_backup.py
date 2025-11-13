#!/usr/bin/env python3
"""Cross-check backup duplicates against NEW_LIBRARY by MD5.

Walks "/Volumes/dotad/Garbage copy" for FLAC files, computes MD5, and
verifies that content exists in NEW_LIBRARY per move plan mapping.

Outputs JSONL with findings and a summary plus a list of any missing MD5s.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable


def md5sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iter_flacs(root: Path) -> Iterable[Path]:
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".flac"):
                yield Path(base) / name


def load_plan_md5_map(plan_csv: Path) -> Dict[str, str]:
    md5_to_dest: Dict[str, str] = {}
    with plan_csv.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            md5 = row.get("md5")
            dest = row.get("destination")
            if md5 and dest:
                md5_to_dest[md5] = dest
    return md5_to_dest


def crosscheck(
    backup_root: Path,
    plan_csv: Path,
    out_jsonl: Path,
    missing_out: Path,
    progress_every: int = 100,
) -> Dict[str, int]:
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    missing_out.parent.mkdir(parents=True, exist_ok=True)

    md5_map = load_plan_md5_map(plan_csv)

    total = 0
    found = 0
    missing = 0

    with out_jsonl.open("w") as jout, missing_out.open("w") as mout:
        for i, p in enumerate(iter_flacs(backup_root), 1):
            total += 1
            try:
                h = md5sum(p)
            except (OSError, IOError) as e:
                err_rec: Dict[str, Any] = {"path": str(p), "error": str(e)}
                jout.write(json.dumps(err_rec) + "\n")
                continue

            dest = md5_map.get(h)
            ok = dest is not None and os.path.exists(dest)
            if ok:
                found += 1
            else:
                missing += 1
                mout.write(f"{h}\t{p}\n")

            rec: Dict[str, Any] = {
                "path": str(p),
                "md5": h,
                "in_new_library": bool(ok),
                "destination": dest or "",
            }
            jout.write(json.dumps(rec) + "\n")

            if i % progress_every == 0:
                print(f"[{i}] found={found} missing={missing}")

    print("\n=== Garbage backup cross-check ===")
    print(f"Backup FLAC files: {total}")
    print(f"Content found in NEW_LIBRARY: {found}")
    print(f"Content NOT found in NEW_LIBRARY: {missing}")

    return {"total": total, "found": found, "missing": missing}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Cross-check backup by MD5 vs NEW_LIBRARY"
    )
    ap.add_argument(
        "--backup-root",
        type=Path,
        default=Path("/Volumes/dotad/Garbage copy"),
    )
    ap.add_argument(
        "--plan",
        type=Path,
        default=Path("artifacts/reports/library_move_plan.csv"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/reports/garbage_backup_crosscheck.jsonl"),
    )
    ap.add_argument(
        "--missing-out",
        type=Path,
        default=Path("artifacts/reports/garbage_backup_missing.tsv"),
    )
    ap.add_argument("--progress-every", type=int, default=100)
    ns = ap.parse_args()

    if not ns.plan.exists():
        print(f"Plan CSV not found: {ns.plan}")
        return 1
    if not ns.backup_root.exists():
        print(f"Backup root not found: {ns.backup_root}")
        return 1

    res = crosscheck(
        ns.backup_root, ns.plan, ns.out, ns.missing_out, ns.progress_every
    )
    return 0 if res.get("missing", 1) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
