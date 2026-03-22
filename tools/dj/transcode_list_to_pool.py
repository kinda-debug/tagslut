#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from mutagen.flac import FLAC  # type: ignore

from tagslut.exec.transcoder import _apply_id3_tags, _run_ffmpeg_transcode  # type: ignore


@dataclass(frozen=True)
class Job:
    source_path: Path
    dest_path: Path


def _read_paths(path: Path) -> list[Path]:
    items: list[Path] = []
    seen: set[Path] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        item = Path(line).expanduser()
        if not item.is_absolute():
            item = (path.parent / item).resolve()
        else:
            item = item.resolve()
        if item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def _dest_rel_path(source_path: Path, source_root: Path) -> Path:
    try:
        rel_path = source_path.relative_to(source_root)
    except ValueError:
        digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:10]
        return Path("_external") / f"{source_path.stem}-{digest}.mp3"
    return rel_path.with_suffix(".mp3")


def _plan_jobs(source_paths: list[Path], *, pool_root: Path, source_root: Path) -> list[Job]:
    jobs: list[Job] = []
    used_destinations: set[Path] = set()
    for source_path in source_paths:
        rel_path = _dest_rel_path(source_path, source_root)
        dest_path = pool_root / rel_path
        if dest_path in used_destinations:
            digest = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:10]
            dest_path = dest_path.with_name(f"{dest_path.stem}-{digest}{dest_path.suffix}")
        used_destinations.add(dest_path)
        jobs.append(Job(source_path=source_path, dest_path=dest_path))
    return jobs


def _transcode_one(job: Job, *, bitrate: int, overwrite: bool) -> dict[str, str]:
    source_path = job.source_path
    dest_path = job.dest_path
    if not source_path.exists():
        return {
            "status": "missing_source",
            "source_path": str(source_path),
            "dest_path": str(dest_path),
        }

    if dest_path.exists() and not overwrite:
        return {
            "status": "existing",
            "source_path": str(source_path),
            "dest_path": str(dest_path),
        }

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg_transcode(source_path, dest_path, bitrate=bitrate, ffmpeg_path=None)
    try:
        flac_tags = FLAC(source_path)
    except Exception:
        flac_tags = None
    _apply_id3_tags(dest_path, flac_tags, prune_existing=True)
    return {
        "status": "transcoded",
        "source_path": str(source_path),
        "dest_path": str(dest_path),
    }


def _write_playlist(path: Path, dest_paths: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U", *[str(item.resolve()) for item in dest_paths]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def transcode_list_to_pool(
    *,
    list_path: Path,
    pool_root: Path,
    source_root: Path,
    batch_dir: Path,
    playlist_name: str,
    bitrate: int = 320,
    jobs: int = 8,
    overwrite: bool = False,
) -> dict[str, object]:
    resolved_list = list_path.expanduser().resolve()
    resolved_pool = pool_root.expanduser().resolve()
    resolved_source_root = source_root.expanduser().resolve()
    resolved_batch_dir = batch_dir.expanduser().resolve()

    source_paths = _read_paths(resolved_list)
    job_rows = _plan_jobs(source_paths, pool_root=resolved_pool, source_root=resolved_source_root)

    results: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        futures = [
            executor.submit(_transcode_one, job, bitrate=bitrate, overwrite=overwrite)
            for job in job_rows
        ]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["source_path"])

    status_counts: dict[str, int] = {}
    destination_by_source = {str(job.source_path): job.dest_path for job in job_rows}
    playlist_paths: list[Path] = []
    for source_path in source_paths:
        dest_path = destination_by_source[str(source_path)]
        if dest_path.exists():
            playlist_paths.append(dest_path)
    for row in results:
        status = row["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    resolved_batch_dir.mkdir(parents=True, exist_ok=True)
    playlist_path = resolved_batch_dir / f"{playlist_name}.m3u"
    _write_playlist(playlist_path, playlist_paths)

    csv_path = resolved_batch_dir / f"{playlist_name}.transcode_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["status", "source_path", "dest_path"])
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    summary = {
        "list_path": str(resolved_list),
        "pool_root": str(resolved_pool),
        "source_root": str(resolved_source_root),
        "batch_dir": str(resolved_batch_dir),
        "playlist_path": str(playlist_path),
        "results_csv": str(csv_path),
        "playlist_name": playlist_name,
        "requested": len(source_paths),
        "playlist_entries": len(playlist_paths),
        "status_counts": status_counts,
    }
    summary_path = resolved_batch_dir / f"{playlist_name}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcode an explicit list of source files into a pool root.")
    parser.add_argument("list_path", help="Text file containing source paths to transcode")
    parser.add_argument("--pool-root", required=True, help="Destination pool root for transcoded MP3s")
    parser.add_argument("--source-root", default="/Volumes/MUSIC/MASTER_LIBRARY", help="Root used to preserve relative layout")
    parser.add_argument("--batch-dir", required=True, help="Output directory for the generated batch playlist and reports")
    parser.add_argument("--playlist-name", default="needs_transcoding_list", help="Generated batch playlist basename")
    parser.add_argument("--bitrate", type=int, default=320, help="Target MP3 bitrate in kbps")
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 8), help="Parallel ffmpeg jobs")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing destination MP3 files")
    args = parser.parse_args()

    summary = transcode_list_to_pool(
        list_path=Path(args.list_path),
        pool_root=Path(args.pool_root),
        source_root=Path(args.source_root),
        batch_dir=Path(args.batch_dir),
        playlist_name=args.playlist_name,
        bitrate=args.bitrate,
        jobs=args.jobs,
        overwrite=bool(args.overwrite),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
