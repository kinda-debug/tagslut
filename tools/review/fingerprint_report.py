#!/usr/bin/env python3
"""Compute Chromaprint fingerprints and report potential near-duplicates."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import List, Dict


def iter_flacs(paths: List[Path]) -> List[Path]:
    out = []
    for root in paths:
        if root.is_file() and root.suffix.lower() == ".flac":
            out.append(root)
        elif root.is_dir():
            out.extend([p for p in root.rglob("*.flac") if not p.name.startswith("._")])
    return out


def fpcalc(path: Path, length: int) -> Dict[str, str] | None:
    cmd = ["fpcalc", "-json", "-length", str(length), str(path)]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        data = json.loads(out)
        return {
            "fingerprint": data.get("fingerprint", ""),
            "duration": str(data.get("duration", "")),
        }
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Fingerprint report using fpcalc")
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--paths-file", type=Path, help="File containing paths (one per line)")
    ap.add_argument("--length", type=int, default=120, help="Fingerprint length in seconds")
    ap.add_argument("--out", type=Path, default=Path("artifacts/fingerprint_report.csv"))
    ap.add_argument("--groups", type=Path, default=Path("artifacts/fingerprint_groups.csv"))
    ap.add_argument("--limit", type=int, help="Limit number of files")
    ap.add_argument("--offset", type=int, default=0, help="Skip first N files")
    args = ap.parse_args()

    files = []
    if args.paths_file:
        path_list = [Path(line.strip()) for line in args.paths_file.read_text().splitlines() if line.strip()]
        files.extend(iter_flacs([p.expanduser().resolve() for p in path_list]))
    if args.paths:
        files.extend(iter_flacs([p.expanduser().resolve() for p in args.paths]))
    if not files:
        print("No FLAC files found.")
        return 1

    if args.offset:
        files = files[args.offset:]
    if args.limit:
        files = files[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for idx, path in enumerate(files, start=1):
        fp = fpcalc(path, args.length)
        if not fp or not fp["fingerprint"]:
            continue
        rows.append({
            "path": str(path),
            "fingerprint": fp["fingerprint"],
            "duration": fp["duration"],
        })
        if idx % 200 == 0 or idx == len(files):
            print(f"[{idx}/{len(files)}] {path.name}")

    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "duration", "fingerprint"])
        w.writeheader()
        w.writerows(rows)

    # Group identical fingerprints (near-duplicate proxy)
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        groups[r["fingerprint"]].append(r["path"])

    with args.groups.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fingerprint", "count", "paths"])
        for fp, paths in groups.items():
            if len(paths) > 1:
                w.writerow([fp, len(paths), " | ".join(paths)])

    print(f"Fingerprinted: {len(rows)}")
    print(f"Report: {args.out}")
    print(f"Groups: {args.groups}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
