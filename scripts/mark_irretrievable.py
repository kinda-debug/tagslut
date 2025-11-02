#!/usr/bin/env python3
"""
scripts/mark_irretrievable.py

Mark entries with status == "not_found" in a repair report as
"irretrievable", add a timestamped note, and remove matching
original paths from /tmp/to_repair.txt (if present).

Usage:
  python3 scripts/mark_irretrievable.py repair_report_apply.json

This writes a backup of the input and a new file
repair_report_apply.marked.json. The operation is reversible using the
backup file.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(obj: Any, path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def normalize_to_list(obj: Any) -> list:
    # Accept list or dict-of-entries; return a list of entry objects.
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        # if values look like entry objects, use values; otherwise wrap
        vals = list(obj.values())
        if all(isinstance(v, (dict, list, str)) for v in vals):
            return vals
        return [obj]
    return [obj]


def extract_original_paths(entry: Any) -> list:
    """Return a list of original paths from an entry.

    Handles: entry['original'] being a string (possibly containing
    literal "\n" escape sequences) or a list of strings.
    """
    orig = entry.get("original") if isinstance(entry, dict) else None
    if not orig:
        return []
    if isinstance(orig, list):
        return [p for p in orig if p]
    if isinstance(orig, str):
        # Some entries contain literal "\n" sequences in the JSON string.
        # Convert escaped-newlines into real newlines, then split.
        s = orig.replace("\\n", "\n")
        return [line for line in s.splitlines() if line.strip()]
    return []


def main():
    if len(sys.argv) < 2:
        print("Usage: mark_irretrievable.py repair_report_apply.json")
        sys.exit(2)

    src = Path(sys.argv[1])
    if not src.exists():
        print(f"File not found: {src}")
        sys.exit(2)

    data = load_json(src)
    items = normalize_to_list(data)

    modified = 0
    removed_paths = set()

    for entry in items:
        if not isinstance(entry, dict):
            continue
        if entry.get("status") == "not_found":
            entry["status"] = "irretrievable"
            ts = datetime.utcnow().isoformat() + "Z"
            entry.setdefault("note", "")
            entry["note"] = (
                f"marked irretrievable on {ts} by mark_irretrievable.py; "
                + entry.get("note", "")
            )
            entry["irretrievable_at"] = ts
            modified += 1

            for p in extract_original_paths(entry):
                removed_paths.add(p)

    # write backup
    bak = src.with_suffix(src.suffix + ".bak")
    bak.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    out = src.with_name(src.stem + ".marked" + src.suffix)
    save_json(items, out)

    # remove lines from /tmp/to_repair.txt that exactly match any removed_paths
    to_repair = Path("/tmp/to_repair.txt")
    removed_lines = 0
    if to_repair.exists():
        raw = to_repair.read_text(encoding="utf-8")
        lines = [ln.rstrip("\n") for ln in raw.splitlines()]
        if lines:
            keep = []
            s = set(removed_paths)
            for ln in lines:
                if ln in s:
                    removed_lines += 1
                else:
                    keep.append(ln)
            out_text = "\n".join(keep) + ("\n" if keep else "")
            to_repair.write_text(out_text, encoding="utf-8")

    print(f"Wrote backup: {bak}")
    print(f"Wrote marked report: {out}")
    print(f"Entries marked irretrievable: {modified}")
    print(
        f"Removed {removed_lines} lines from /tmp/to_repair.txt "
        "(if present)"
    )


if __name__ == "__main__":
    main()
