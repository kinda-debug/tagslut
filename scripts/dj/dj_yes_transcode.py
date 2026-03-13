#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from tagslut.dj.transcode import (
    TrackRow,
    assign_output_paths,
    dedupe_tracks,
    load_tracks,
    run_checked,
    transcode_one,
)

def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH")

def write_csv(path: Path, rows: List[Dict], fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input-xlsx", type=Path, required=True)
    p.add_argument("--sheet", type=str, default=None)
    p.add_argument("--output-root", type=Path, required=True)
    p.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 4))
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()

def main():

    args = parse_args()
    check_ffmpeg()

    if not args.input_xlsx.exists():
        raise RuntimeError(f"Missing XLSX: {args.input_xlsx}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_dir = args.output_root / f"_manifests_{timestamp}"

    tracks, dropped_missing, _headers = load_tracks(args.input_xlsx, args.sheet)
    deduped, dropped_dupes = dedupe_tracks(tracks)
    assign_output_paths(deduped, args.output_root)

    manifest_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        manifest_dir / "dropped_missing.csv",
        dropped_missing,
        ["row_num", "reason", "path"],
    )

    write_csv(
        manifest_dir / "dropped_duplicates.csv",
        dropped_dupes,
        ["dedupe_key", "kept_row", "kept_path", "dropped_row", "dropped_path", "reason"],
    )

    jobs: List[TrackRow] = []
    skipped_existing = 0

    for t in deduped:

        if not args.overwrite and t.output_path.exists():
            skipped_existing += 1
            continue

        if t.source_path.suffix.lower() == ".mp3" and not args.overwrite:
            skipped_existing += 1
            continue

        jobs.append(t)

    if args.dry_run:
        print("Dry run:")
        print("jobs:", len(jobs))
        print("skipped_existing:", skipped_existing)
        return 0

    total = len(jobs)
    completed = 0
    ok = 0
    failures: List[Dict] = []

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:

        futures = [pool.submit(transcode_one, t, args.overwrite) for t in jobs]

        for future in as_completed(futures):

            result = future.result()

            status, track, error = result[:3]

            completed += 1

            if status == "ok":
                ok += 1
            elif status == "skipped_existing":
                skipped_existing += 1
            else:
                failures.append(
                    {
                        "row": track.row_num,
                        "source": str(track.source_path),
                        "output": str(track.output_path),
                        "error": error,
                    }
                )

            if completed % 50 == 0 or completed == total:
                print(
                    f"{completed}/{total}  ok={ok}  skipped={skipped_existing}  failed={len(failures)}"
                )

    if failures:
        write_csv(
            manifest_dir / "transcode_failures.csv",
            failures,
            ["row", "source", "output", "error"],
        )

    final = {
        "ok": ok,
        "skipped_existing": skipped_existing,
        "failed": len(failures),
        "manifest_dir": str(manifest_dir),
    }

    print(json.dumps(final, indent=2))

    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
