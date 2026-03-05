#!/usr/bin/env python3
"""
Apply ISRCs from a fetch report CSV to local files.

CSV must include:
  - path
  - isrc

Only rows with non-empty isrc are written.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError, TSRC


def _get_id3(path: Path) -> ID3 | None:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply ISRCs from a CSV report.")
    ap.add_argument("--report", type=Path, required=True, help="CSV report with path,isrc columns")
    ap.add_argument("--execute", action="store_true", help="Write TSRC tags to files")
    ap.add_argument("--out", type=Path, help="Optional output CSV with applied rows")
    args = ap.parse_args()

    out_path = args.out
    out_file = None
    writer = None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_file = out_path.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(out_file, fieldnames=["path", "isrc", "status"])
        writer.writeheader()

    applied = 0
    skipped = 0
    missing = 0
    errors = 0

    with args.report.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "path" not in reader.fieldnames or "isrc" not in reader.fieldnames:
            raise SystemExit("CSV must contain 'path' and 'isrc' columns.")
        for row in reader:
            path = Path(row["path"])
            isrc = (row.get("isrc") or "").strip()
            if not isrc:
                skipped += 1
                if writer:
                    writer.writerow({"path": str(path), "isrc": isrc, "status": "empty_isrc"})
                continue
            if not path.exists():
                missing += 1
                if writer:
                    writer.writerow({"path": str(path), "isrc": isrc, "status": "missing_file"})
                continue
            tags = _get_id3(path)
            if tags is None:
                errors += 1
                if writer:
                    writer.writerow({"path": str(path), "isrc": isrc, "status": "tag_read_error"})
                continue
            if args.execute:
                tags["TSRC"] = TSRC(encoding=3, text=isrc)
                tags.save(path, v2_version=3)
            applied += 1
            if writer:
                writer.writerow({"path": str(path), "isrc": isrc, "status": "applied"})

    if out_file:
        out_file.close()

    print(f"applied={applied} skipped={skipped} missing={missing} errors={errors}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
