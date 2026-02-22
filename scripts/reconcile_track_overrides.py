#!/usr/bin/env python3
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
import re

TRACK_OVERRIDES = Path("config/dj/track_overrides.csv")


def _normalize_variants(path_str: str) -> list[str]:
    variants = []
    variants.append(path_str)
    variants.append(path_str + ".flac")
    variants.append(re.sub(r"\s+\(1\)(\.[^.]+)$", r"\1", path_str))

    if " - " in path_str:
        variants.append(path_str.replace(" - ", " – "))
    if " – " in path_str:
        variants.append(path_str.replace(" – ", " - "))

    p = Path(path_str)
    if p.suffix.lower() == ".flac" and p.stem.lower().endswith(".flac"):
        variants.append(str(p.with_name(p.stem[:-5] + ".flac")))

    for base in list(variants):
        bp = Path(base)
        if bp.suffix.lower() == ".flac" and bp.stem.lower().endswith(".flac"):
            fixed = str(bp.with_name(bp.stem[:-5] + ".flac"))
            variants.append(fixed)
        if " - " in base:
            variants.append(base.replace(" - ", " – "))
        if " – " in base:
            variants.append(base.replace(" – ", " - "))
        if not base.endswith(".flac"):
            variants.append(base + ".flac")
        stripped = re.sub(r"\s+\(1\)(\.[^.]+)$", r"\1", base)
        if stripped != base:
            variants.append(stripped)
            if not stripped.endswith(".flac"):
                variants.append(stripped + ".flac")

    seen = set()
    unique = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def main() -> int:
    if not TRACK_OVERRIDES.exists():
        print(f"ERROR: {TRACK_OVERRIDES} does not exist")
        return 2

    rows = []
    corrected = []
    missing = []

    with TRACK_OVERRIDES.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            rows.append(row)

    output_rows = []
    reconciled_tag = f"# Paths reconciled {dt.datetime.now().strftime('%Y-%m-%d')} via reconcile_track_overrides.py"
    tag_inserted = False

    for row in rows:
        if not row:
            output_rows.append(row)
            continue
        if row[0].strip().startswith("#"):
            output_rows.append(row)
            continue

        while len(row) < 6:
            row.append("")

        path_value = row[0].strip()
        if not path_value:
            output_rows.append(row)
            continue

        p = Path(path_value)
        if p.exists():
            output_rows.append(row)
            continue

        fixed_path = None
        for candidate in _normalize_variants(path_value):
            if Path(candidate).exists():
                fixed_path = candidate
                break

        if fixed_path:
            if not tag_inserted:
                output_rows.append([reconciled_tag])
                tag_inserted = True
            corrected.append((path_value, fixed_path))
            row[0] = fixed_path
            output_rows.append(row)
        else:
            missing.append(path_value)
            output_rows.append(row)

    print(f"{len(corrected)} paths corrected")
    for old, new in corrected[:10]:
        print(f"- {old} -> {new}")

    print(f"{len(missing)} truly missing")
    for m in missing:
        print(m)

    # rewrite file in place
    with TRACK_OVERRIDES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        for row in output_rows:
            writer.writerow(row)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
