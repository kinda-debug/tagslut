#!/usr/bin/env python3
"""
plan_move_skipped_to_fix.py

Generate a MOVE-only plan CSV to relocate SKIP rows from another plan into a FIX area.

Typical usage:
  1) Plan canonical promotion (MOVE + SKIP)
  2) Move MOVE rows into FINAL library
  3) Move SKIP rows into FIX for manual retagging / correction

This script does NOT move files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()


def _bucket_from_reason(reason: str) -> str:
    head = (reason or "").split(":", 1)[0].strip().lower()
    if head in {"path_too_long", "missing_tags", "dest_exists", "conflict_same_dest"}:
        return head
    if head:
        return head
    return "skipped"


def _truncate_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8", "replace")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes]
    # Avoid splitting a multibyte sequence.
    while True:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]


def _dest_for_skip(
    src: Path,
    fix_root: Path,
    bucket: str,
    *,
    source_root: Path | None,
) -> Path:
    if bucket == "missing_tags" and source_root is not None:
        try:
            rel = src.resolve().relative_to(source_root.resolve())
            return fix_root / bucket / rel
        except Exception:
            pass

    h = _sha1_text(str(src))[:8]
    name = src.name
    # Keep extension and ensure filename component stays well under typical limits.
    stem = src.stem
    suffix = src.suffix
    safe_stem = _truncate_bytes(stem, 160)
    name = f"{h}__{safe_stem}{suffix}"
    return fix_root / bucket / name


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Plan moving SKIP rows to a FIX directory (MOVE-only plan)")
    ap.add_argument("plan_csv", type=Path, help="Input plan CSV that contains SKIP rows")
    ap.add_argument("--fix-root", required=True, type=Path, help="Destination root for skipped files")
    ap.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="If provided, missing_tags items preserve relative path under this root",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory for plan+summary")
    ap.add_argument("--stamp", default=None, help="Optional timestamp stamp override (default: now UTC)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    plan_csv = args.plan_csv.expanduser().resolve()
    fix_root = args.fix_root.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve() if args.source_root else None
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or _now_stamp()

    out_plan = out_dir / f"plan_move_skipped_to_fix_{stamp}.csv"
    out_summary = out_dir / f"plan_move_skipped_to_fix_summary_{stamp}.json"

    rows: list[dict[str, str]] = []
    buckets: Counter[str] = Counter()

    with plan_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            action = (row.get("action") or "").strip().upper()
            if action != "SKIP":
                continue
            src_s = (row.get("path") or "").strip()
            if not src_s:
                continue
            src = Path(src_s)
            reason = (row.get("reason") or "").strip()
            bucket = _bucket_from_reason(reason)
            buckets[bucket] += 1

            dest = _dest_for_skip(src, fix_root, bucket, source_root=source_root)
            rows.append(
                {
                    "action": "MOVE",
                    "path": src_s,
                    "dest_path": str(dest),
                    "reason": reason or "skipped",
                }
            )

    with out_plan.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["action", "path", "dest_path", "reason"])
        w.writeheader()
        w.writerows(rows)

    summary = {
        "stamp": stamp,
        "input_plan_csv": str(plan_csv),
        "fix_root": str(fix_root),
        "source_root": str(source_root) if source_root else None,
        "skip_move_rows": len(rows),
        "bucket_counts": dict(buckets),
        "plan_csv": str(out_plan),
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Planned MOVE rows (skips -> FIX): {len(rows)}")
    if buckets:
        for k, v in buckets.most_common():
            print(f"  {k}: {v}")
    print(f"Wrote: {out_plan}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

