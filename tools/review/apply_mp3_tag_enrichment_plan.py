#!/usr/bin/env python3
"""
Apply MP3 tag enrichment actions from a CSV plan.

Expected input format (from data/mp3_tag_enrichment_plan.csv):
cluster_id,keep_path,tag_field,current_value,proposed_value,source_path

Default behavior is dry-run. Use --execute to write ID3 tags.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import COMM, ID3, ID3NoHeaderError, TBPM, TCON, TDRC, TIT2, TKEY, TALB, TPE1, TSRC, TXXX


@dataclass(frozen=True)
class PlanRow:
    keep_path: Path
    tag_field: str
    proposed_value: str
    source_path: str


@dataclass
class Stats:
    files_seen: int = 0
    files_missing: int = 0
    files_updated: int = 0
    rows_seen: int = 0
    rows_invalid: int = 0
    rows_skipped_existing: int = 0
    rows_skipped_empty: int = 0
    rows_applied: int = 0


def normalize_field(field: str) -> str:
    key = (field or "").strip().lower()
    if key.startswith("id3_"):
        key = key[4:]
    return key


def text_frame_missing(tags: ID3, frame_id: str) -> bool:
    frame = tags.get(frame_id)
    if frame is None:
        return True
    values = getattr(frame, "text", None)
    if not values:
        return True
    return not any(str(v).strip() for v in values)


def has_txxx_value(tags: ID3, desc: str) -> bool:
    desc_fold = desc.casefold()
    for frame in tags.getall("TXXX"):
        if str(getattr(frame, "desc", "")).casefold() != desc_fold:
            continue
        values = getattr(frame, "text", None)
        if values and any(str(v).strip() for v in values):
            return True
    return False


def has_comment_value(tags: ID3) -> bool:
    for frame in tags.getall("COMM"):
        values = getattr(frame, "text", None)
        if values and any(str(v).strip() for v in values):
            return True
    return False


def set_field_if_missing(tags: ID3, field: str, value: str, force: bool) -> bool:
    val = value.strip()
    if not val:
        return False

    if field == "title":
        if not force and not text_frame_missing(tags, "TIT2"):
            return False
        tags["TIT2"] = TIT2(encoding=3, text=val)
        return True
    if field == "artist":
        if not force and not text_frame_missing(tags, "TPE1"):
            return False
        tags["TPE1"] = TPE1(encoding=3, text=val)
        return True
    if field == "album":
        if not force and not text_frame_missing(tags, "TALB"):
            return False
        tags["TALB"] = TALB(encoding=3, text=val)
        return True
    if field == "year":
        if not force and not text_frame_missing(tags, "TDRC"):
            return False
        tags["TDRC"] = TDRC(encoding=3, text=val)
        return True
    if field == "bpm":
        if not force and not text_frame_missing(tags, "TBPM"):
            return False
        tags["TBPM"] = TBPM(encoding=3, text=val)
        return True
    if field == "key":
        changed = False
        if force or text_frame_missing(tags, "TKEY"):
            tags["TKEY"] = TKEY(encoding=3, text=val)
            changed = True
        if force or not has_txxx_value(tags, "INITIALKEY"):
            tags["TXXX:INITIALKEY"] = TXXX(encoding=3, desc="INITIALKEY", text=val)
            changed = True
        return changed
    if field == "genre":
        if not force and not text_frame_missing(tags, "TCON"):
            return False
        tags["TCON"] = TCON(encoding=3, text=val)
        return True
    if field == "label":
        if not force and has_txxx_value(tags, "LABEL"):
            return False
        tags["TXXX:LABEL"] = TXXX(encoding=3, desc="LABEL", text=val)
        return True
    if field == "remixer":
        if not force and has_txxx_value(tags, "REMIXER"):
            return False
        tags["TXXX:REMIXER"] = TXXX(encoding=3, desc="REMIXER", text=val)
        return True
    if field == "isrc":
        if not force and not text_frame_missing(tags, "TSRC"):
            return False
        tags["TSRC"] = TSRC(encoding=3, text=val)
        return True
    if field == "comment":
        if not force and has_comment_value(tags):
            return False
        tags.delall("COMM")
        tags.add(COMM(encoding=3, lang="eng", desc="", text=val))
        return True

    return False


def load_plan(plan_path: Path) -> list[PlanRow]:
    rows: list[PlanRow] = []
    with plan_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keep_path_raw = (row.get("keep_path") or "").strip()
            tag_field_raw = (row.get("tag_field") or "").strip()
            proposed_value = (row.get("proposed_value") or "").strip()
            source_path = (row.get("source_path") or "").strip()
            if not keep_path_raw or not tag_field_raw:
                continue
            rows.append(
                PlanRow(
                    keep_path=Path(keep_path_raw),
                    tag_field=normalize_field(tag_field_raw),
                    proposed_value=proposed_value,
                    source_path=source_path,
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply MP3 tag enrichment plan CSV to files")
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("data/mp3_tag_enrichment_plan.csv"),
        help="Path to enrichment plan CSV",
    )
    parser.add_argument("--execute", action="store_true", help="Write tags (default: dry-run)")
    parser.add_argument("--force", action="store_true", help="Overwrite non-empty existing tag values")
    parser.add_argument("--limit-files", type=int, help="Only process first N files")
    parser.add_argument("--progress-interval", type=int, default=50, help="Progress print interval")
    args = parser.parse_args()

    plan_path = args.plan.expanduser().resolve()
    if not plan_path.exists():
        raise SystemExit(f"Plan not found: {plan_path}")

    rows = load_plan(plan_path)
    if not rows:
        print("No enrichment rows found in plan.")
        return 0

    by_file: dict[Path, list[PlanRow]] = defaultdict(list)
    for row in rows:
        by_file[row.keep_path].append(row)

    files = sorted(by_file.keys())
    if args.limit_files:
        files = files[: int(args.limit_files)]

    stats = Stats()
    stats.rows_seen = len(rows)

    if not args.execute:
        print("DRY-RUN: use --execute to write tags")

    for idx, file_path in enumerate(files, start=1):
        stats.files_seen += 1
        if not file_path.exists():
            stats.files_missing += 1
            print(f"[MISSING] {file_path}")
            continue

        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()
        except Exception as exc:
            stats.rows_invalid += len(by_file[file_path])
            print(f"[ERROR] {file_path} :: could not open ID3 ({exc})")
            continue

        file_changed = False
        for row in by_file[file_path]:
            if not row.proposed_value.strip():
                stats.rows_skipped_empty += 1
                continue

            changed = set_field_if_missing(tags, row.tag_field, row.proposed_value, force=bool(args.force))
            if changed:
                file_changed = True
                stats.rows_applied += 1
                print(f"[APPLY] {file_path} :: {row.tag_field} <- {row.proposed_value}")
            else:
                stats.rows_skipped_existing += 1
                print(f"[SKIP]  {file_path} :: {row.tag_field} (already set)")

        if file_changed:
            stats.files_updated += 1
            if args.execute:
                tags.save(file_path)

        if args.progress_interval > 0 and idx % int(args.progress_interval) == 0:
            print(f"[PROGRESS] files={idx}/{len(files)}")

    print("\nSummary")
    print(f"  files_seen:            {stats.files_seen}")
    print(f"  files_missing:         {stats.files_missing}")
    print(f"  files_updated:         {stats.files_updated}")
    print(f"  rows_seen:             {stats.rows_seen}")
    print(f"  rows_applied:          {stats.rows_applied}")
    print(f"  rows_skipped_existing: {stats.rows_skipped_existing}")
    print(f"  rows_skipped_empty:    {stats.rows_skipped_empty}")
    print(f"  rows_invalid:          {stats.rows_invalid}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
