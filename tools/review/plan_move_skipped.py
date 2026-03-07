#!/usr/bin/env python3
"""
plan_move_skipped.py

Generate a MOVE-only plan CSV from SKIP rows in another plan CSV.

Typical usage:
  1) Plan canonical promotion (MOVE + SKIP)
  2) Route SKIP rows by reason bucket:
       - missing_tags -> FIX
       - dest_exists  -> DISCARD
       - other risky cases -> manual handling

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


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", "ignore")).hexdigest()


def bucket_from_reason(reason: str) -> str:
    head = (reason or "").split(":", 1)[0].strip().lower()
    if head:
        return head
    return "skipped"


def _truncate_bytes(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8", "replace")
    if len(raw) <= max_bytes:
        return text
    clipped = raw[:max_bytes]
    while True:
        try:
            return clipped.decode("utf-8")
        except UnicodeDecodeError:
            clipped = clipped[:-1]


def _normalize_buckets(value: str) -> set[str]:
    buckets = set()
    for item in (value or "").split(","):
        item = item.strip().lower()
        if item:
            buckets.add(item)
    return buckets


def _dest_for_skip(
    src: Path,
    target_root: Path,
    bucket: str,
    *,
    source_root: Path | None,
) -> Path:
    if source_root is not None and bucket in {"missing_tags", "dest_exists"}:
        try:
            rel = src.resolve().relative_to(source_root.resolve())
            return target_root / bucket / rel
        except Exception:
            pass

    h = _sha1_text(str(src))[:8]
    stem = _truncate_bytes(src.stem, 160)
    return target_root / bucket / f"{h}__{stem}{src.suffix}"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Plan moving SKIP rows from an existing plan into another root"
    )
    ap.add_argument("plan_csv", type=Path, help="Input plan CSV that contains SKIP rows")
    ap.add_argument("--target-root", required=True, type=Path, help="Destination root for matched SKIP rows")
    ap.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="If provided, some buckets preserve relative path under this root",
    )
    ap.add_argument(
        "--include-buckets",
        default="",
        help="Comma-separated skip buckets to include (default: all buckets)",
    )
    ap.add_argument(
        "--exclude-buckets",
        default="",
        help="Comma-separated skip buckets to exclude",
    )
    ap.add_argument(
        "--output-prefix",
        default="plan_move_skipped",
        help="Prefix for generated plan/summary files",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/compare"), help="Output directory for plan+summary")
    ap.add_argument("--stamp", default=None, help="Optional timestamp stamp override (default: now UTC)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    plan_csv = args.plan_csv.expanduser().resolve()
    target_root = args.target_root.expanduser().resolve()
    source_root = args.source_root.expanduser().resolve() if args.source_root else None
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = args.stamp or _now_stamp()
    include_buckets = _normalize_buckets(args.include_buckets)
    exclude_buckets = _normalize_buckets(args.exclude_buckets)

    out_plan = out_dir / f"{args.output_prefix}_{stamp}.csv"
    out_summary = out_dir / f"{args.output_prefix}_summary_{stamp}.json"

    rows: list[dict[str, str]] = []
    buckets: Counter[str] = Counter()

    with plan_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            action = (row.get("action") or "").strip().upper()
            if action != "SKIP":
                continue

            src_s = (row.get("path") or "").strip()
            if not src_s:
                continue

            reason = (row.get("reason") or "").strip()
            bucket = bucket_from_reason(reason)
            if include_buckets and bucket not in include_buckets:
                continue
            if bucket in exclude_buckets:
                continue

            src = Path(src_s)
            dest = _dest_for_skip(src, target_root, bucket, source_root=source_root)
            buckets[bucket] += 1
            rows.append(
                {
                    "action": "MOVE",
                    "path": src_s,
                    "dest_path": str(dest),
                    "reason": reason or "skipped",
                }
            )

    with out_plan.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["action", "path", "dest_path", "reason"])
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "stamp": stamp,
        "input_plan_csv": str(plan_csv),
        "target_root": str(target_root),
        "source_root": str(source_root) if source_root else None,
        "selected_rows": len(rows),
        "bucket_counts": dict(buckets),
        "include_buckets": sorted(include_buckets),
        "exclude_buckets": sorted(exclude_buckets),
        "plan_csv": str(out_plan),
        "summary_json": str(out_summary),
    }
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Planned MOVE rows (skips -> target): {len(rows)}")
    if buckets:
        for bucket, count in buckets.most_common():
            print(f"  {bucket}: {count}")
    print(f"Wrote: {out_plan}")
    print(f"Wrote: {out_summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
