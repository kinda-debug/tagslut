#!/usr/bin/env python3
"""Merge and dedupe DJ library folders using keeper selection rules.

Scans source roots, hashes files, selects keepers per duplicate group using
`tagslut.core.keeper_selection.select_keeper_for_group`, and consolidates
into a new output root.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from tagslut.core.keeper_selection import select_keeper_for_group
from tagslut.storage.models import AudioFile, DuplicateGroup
from tagslut.utils.zones import Zone, ZoneConfig, ZoneManager, PathPriority, DEFAULT_ZONE_PRIORITY

AUDIO_EXTS = {".mp3", ".m4a", ".aiff", ".aif", ".wav", ".flac"}


@dataclass(frozen=True)
class FileEntry:
    path: Path
    root: Path
    rel: Path
    sha256: str
    audio: AudioFile


def _iter_audio_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in AUDIO_EXTS:
            yield path


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _audio_file(path: Path, sha256: str) -> AudioFile:
    size = path.stat().st_size
    metadata: dict[str, object] = {}
    duration = 0.0
    sample_rate = 0
    bitrate = 0
    bit_depth = 0
    integrity_state = "valid"

    try:
        from mutagen import File as MutagenFile  # type: ignore
    except Exception:
        MutagenFile = None

    if MutagenFile is not None:
        try:
            audio = MutagenFile(path)
        except Exception:
            audio = None
        if audio is not None:
            info = getattr(audio, "info", None)
            if info is not None:
                duration = float(getattr(info, "length", 0.0) or 0.0)
                sample_rate = int(getattr(info, "sample_rate", 0) or 0)
                bitrate = int(getattr(info, "bitrate", 0) or 0)
                bit_depth = int(getattr(info, "bits_per_sample", 0) or 0)
            tags = getattr(audio, "tags", None)
            if tags:
                for key in ("artist", "album", "title"):
                    try:
                        value = tags.get(key)
                    except Exception:
                        value = None
                    if value:
                        if isinstance(value, (list, tuple)):
                            metadata[key] = value[0]
                        else:
                            metadata[key] = value

    return AudioFile(
        path=path,
        checksum=sha256,
        duration=duration,
        bit_depth=bit_depth,
        sample_rate=sample_rate,
        bitrate=bitrate,
        metadata=metadata,
        size=size,
        integrity_state=integrity_state,
        sha256=sha256,
        zone=Zone.ACCEPTED,
    )


def _build_zone_manager(roots: list[Path]) -> ZoneManager:
    priority = DEFAULT_ZONE_PRIORITY[Zone.ACCEPTED]
    zone_configs = [
        ZoneConfig(zone=Zone.ACCEPTED, paths=tuple(roots), priority=priority, description="DJ library roots")
    ]
    path_priorities = [PathPriority(path=root, priority=10, description="DJ source") for root in roots]
    return ZoneManager(zone_configs=zone_configs, path_priorities=path_priorities, default_zone=Zone.ACCEPTED)


def _resolve_dest(out_root: Path, entry: FileEntry, used: dict[Path, int]) -> Path:
    dest = out_root / entry.rel
    if dest not in used and not dest.exists():
        used[dest] = 1
        return dest
    count = used.get(dest, 1)
    while True:
        suffix = f"__dup{count}"
        candidate = dest.with_name(f"{dest.stem}{suffix}{dest.suffix}")
        if candidate not in used and not candidate.exists():
            used[candidate] = 1
            return candidate
        count += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge and dedupe DJ library folders.")
    parser.add_argument("--src", action="append", required=True, help="Source root (repeatable)")
    parser.add_argument("--out", required=True, help="Output root for merged DJ library")
    parser.add_argument("--execute", action="store_true", help="Copy keepers into output root")
    parser.add_argument("--report-dir", default=None, help="Directory for plan/report outputs")
    args = parser.parse_args()

    roots = [Path(p).expanduser().resolve() for p in args.src]
    out_root = Path(args.out).expanduser().resolve()
    report_dir = Path(args.report_dir).expanduser().resolve() if args.report_dir else (out_root / "_merge_reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    for root in roots:
        if not root.exists():
            raise SystemExit(f"Missing source root: {root}")

    zone_manager = _build_zone_manager(roots)

    entries: list[FileEntry] = []
    print("Scanning source roots...")
    for root in roots:
        for path in _iter_audio_files(root):
            rel = path.relative_to(root)
            sha256 = _hash_file(path)
            audio = _audio_file(path, sha256)
            entries.append(FileEntry(path=path, root=root, rel=rel, sha256=sha256, audio=audio))

    print(f"Found {len(entries)} audio files")

    by_hash: dict[str, list[FileEntry]] = {}
    for entry in entries:
        by_hash.setdefault(entry.sha256, []).append(entry)

    used_dests: dict[Path, int] = {}
    plan_rows: list[dict[str, str]] = []
    decision_rows: list[dict[str, object]] = []

    dup_groups = 0
    for sha, group_entries in by_hash.items():
        if len(group_entries) == 1:
            entry = group_entries[0]
            dest = _resolve_dest(out_root, entry, used_dests)
            plan_rows.append(
                {
                    "action": "copy",
                    "reason": "unique",
                    "source_path": str(entry.path),
                    "dest_path": str(dest),
                    "sha256": sha,
                }
            )
            continue

        dup_groups += 1
        group = DuplicateGroup(
            group_id=sha,
            files=[e.audio for e in group_entries],
            similarity=1.0,
            source="checksum",
        )
        selection = select_keeper_for_group(group, zone_manager)
        keeper = selection.keeper
        keeper_path = keeper.path if keeper else None

        for decision in selection.decisions:
            entry = next(e for e in group_entries if e.path == decision.file.path)
            dest = _resolve_dest(out_root, entry, used_dests) if decision.action == "KEEP" else Path("")
            plan_rows.append(
                {
                    "action": "copy" if decision.action == "KEEP" else "skip",
                    "reason": decision.reason,
                    "source_path": str(entry.path),
                    "dest_path": str(dest) if decision.action == "KEEP" else "",
                    "sha256": sha,
                }
            )
            decision_rows.append(
                {
                    "sha256": sha,
                    "action": decision.action,
                    "reason": decision.reason,
                    "source_path": str(entry.path),
                    "keeper_path": str(keeper_path) if keeper_path else None,
                    "evidence": decision.evidence,
                }
            )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plan_path = report_dir / f"dj_library_merge_plan_{timestamp}.csv"
    decisions_path = report_dir / f"dj_library_merge_decisions_{timestamp}.jsonl"

    with plan_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["action", "reason", "source_path", "dest_path", "sha256"],
        )
        writer.writeheader()
        writer.writerows(plan_rows)

    with decisions_path.open("w", encoding="utf-8") as handle:
        for row in decision_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Duplicate groups: {dup_groups}")
    print(f"Plan: {plan_path}")
    print(f"Decisions: {decisions_path}")

    if not args.execute:
        print("Plan-only run; no files copied.")
        return 0

    print("Copying keepers into output root...")
    copied = 0
    skipped = 0
    out_root.mkdir(parents=True, exist_ok=True)
    for row in plan_rows:
        if row["action"] != "copy":
            skipped += 1
            continue
        src = Path(row["source_path"])
        dst = Path(row["dest_path"])
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
        copied += 1

    print(f"Copied: {copied}")
    print(f"Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
