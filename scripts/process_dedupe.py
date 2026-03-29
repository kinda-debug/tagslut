#!/usr/bin/env python3
"""Copy pool tracks missing from MP3_LIBRARY and delete duplicates.

Uses a reconciliation plan CSV (columns: mp3_root, mp3_path, duplicate_roots, ...)
to:
  1) Copy DJ_POOL_MANUAL_MP3 entries that are NOT already in MP3_LIBRARY into
     MP3_LIBRARY (preserving relative path).
  2) Delete duplicate files in DJ_LIBRARY or DJ_POOL_MANUAL_MP3 whose
     duplicate_roots include MP3_LIBRARY.

Defaults to dry-run; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import copy
import csv
import os
import shlex
import shutil
from collections import Counter
from pathlib import Path

from mutagen.id3 import ID3, ID3NoHeaderError


USEFUL_FRAME_KEYS = (
    "TBPM",
    "TKEY",
    "TCON",
    "TXXX:INITIALKEY",
    "TXXX:LABEL",
    "TXXX:ENERGY",
    "TXXX:OPENKEY",
    "TXXX:KEY",
    "TXXX:1T_ENERGY",
    "TXXX:1T_DANCEABILITY",
)


def _load_env_exports(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export"):
            line = line[len("export"):].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        try:
            value = shlex.split(val, posix=True)[0]
        except ValueError:
            value = val.strip('"')
        os.environ.setdefault(key, value)


def _plan_match_key(row: dict[str, str]) -> tuple[str, str]:
    isrc = (row.get("mp3_isrc") or "").strip().upper()
    if isrc:
        return ("isrc", isrc)
    flac_path = (row.get("flac_path") or "").strip()
    if flac_path:
        return ("flac", flac_path)
    artist = (row.get("mp3_artist") or "").strip().casefold()
    title = (row.get("mp3_title") or "").strip().casefold()
    return ("title", f"{artist}|{title}")


def _load_id3(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def _frame_has_value(tags: ID3, key: str) -> bool:
    frame = tags.get(key)
    if frame is None:
        return False
    text = getattr(frame, "text", None)
    if text is not None:
        return any(str(v).strip() for v in text)
    data = getattr(frame, "data", None)
    if data is not None:
        return bool(data)
    return True


def _copy_useful_frames(src_path: Path, dst_path: Path) -> int:
    if not src_path.exists() or not dst_path.exists():
        return 0
    src = _load_id3(src_path)
    dst = _load_id3(dst_path)
    copied = 0
    changed = False
    for key in USEFUL_FRAME_KEYS:
        if _frame_has_value(dst, key):
            continue
        frame = src.get(key)
        if frame is None:
            continue
        dst[key] = copy.deepcopy(frame)
        copied += 1
        changed = True
    if changed:
        dst.save(dst_path, v2_version=3)
    return copied


def main() -> None:
    ap = argparse.ArgumentParser(description="Copy missing pool tracks and dedupe DJ roots using a plan CSV.")
    ap.add_argument("--plan", required=True, help="Path to mp3_reconcile_plan_*.csv")
    ap.add_argument("--env-file", default=None, help="Optional env_exports.sh path (auto-loaded if present).")
    ap.add_argument("--execute", action="store_true", help="Apply changes (default is dry-run).")
    ap.add_argument("--verbose", action="store_true", help="Print each action.")
    args = ap.parse_args()

    script_root = Path(__file__).resolve().parent
    env_file = Path(args.env_file) if args.env_file else script_root.parent / "env_exports.sh"
    _load_env_exports(env_file)

    plan_path = Path(args.plan).expanduser()
    if not plan_path.exists():
        raise SystemExit(f"Plan CSV not found: {plan_path}")

    mp3_root = Path(os.environ.get("MP3_LIBRARY", "")).expanduser()
    dj_root = Path(os.environ.get("DJ_LIBRARY", "")).expanduser()
    pool_root = Path(os.environ.get("DJ_POOL_MANUAL_MP3", "")).expanduser()
    print(f"Dry-run: {not args.execute}")
    print(f"Plan: {plan_path}")
    print(f"MP3_LIBRARY: {mp3_root}")
    print(f"DJ_LIBRARY: {dj_root}")
    print(f"DJ_POOL_MANUAL_MP3: {pool_root}")
    if not mp3_root:
        raise SystemExit("MP3_LIBRARY is not set")
    if not pool_root:
        raise SystemExit("DJ_POOL_MANUAL_MP3 is not set")

    copy_ops: list[tuple[Path, Path]] = []
    delete_paths: list[Path] = []
    tag_sync_ops: list[tuple[Path, Path]] = []
    root_counts: Counter[str] = Counter()
    mp3_library_rows: dict[tuple[str, str], Path] = {}
    pending_duplicate_rows: list[dict[str, str]] = []

    with plan_path.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            root = row.get("mp3_root", "")
            root_counts[root] += 1
            mp3_path = Path(row.get("mp3_path", ""))
            dups = row.get("duplicate_roots", "")

            if root == "MP3_LIBRARY":
                mp3_library_rows[_plan_match_key(row)] = mp3_path

            if root.endswith("DJ_POOL_MANUAL_MP3") and "MP3_LIBRARY" not in dups:
                try:
                    rel = mp3_path.relative_to(pool_root)
                except ValueError:
                    continue
                dest = (mp3_root / rel).resolve()
                if not dest.exists():
                    copy_ops.append((mp3_path, dest))

            if root in ("DJ_LIBRARY", "DJ_POOL_MANUAL_MP3") and "MP3_LIBRARY" in dups:
                delete_paths.append(mp3_path)
                pending_duplicate_rows.append(row)

    for row in pending_duplicate_rows:
        src = Path(row.get("mp3_path", ""))
        dst = mp3_library_rows.get(_plan_match_key(row))
        if dst is not None and dst != src:
            tag_sync_ops.append((src, dst))

    print(f"Plan roots: {dict(root_counts)}")
    print(f"To copy from pool -> MP3_LIBRARY: {len(copy_ops)}")
    print(f"To sync useful tags into MP3_LIBRARY: {len(tag_sync_ops)}")
    print(f"To delete duplicates in DJ roots: {len(delete_paths)}")

    if not copy_ops and not delete_paths:
        if not root_counts.get("DJ_POOL_MANUAL_MP3"):
            print("No DJ_POOL_MANUAL_MP3 rows exist in this plan.")
        if not root_counts.get("MP3_LIBRARY"):
            print("No MP3_LIBRARY rows exist in this plan.")
        print("This plan cannot drive any pool -> MP3 copy or duplicate deletion.")

    if args.verbose:
        for src, dst in copy_ops:
            print(f"COPY {src} -> {dst}")
        for src, dst in tag_sync_ops:
            print(f"SYNC {src} -> {dst}")
        for path in delete_paths:
            print(f"DEL  {path}")

    if not args.execute:
        return

    copied = 0
    for src, dst in copy_ops:
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    synced_files = 0
    synced_frames = 0
    for src, dst in tag_sync_ops:
        copied_frames = _copy_useful_frames(src, dst)
        if copied_frames:
            synced_files += 1
            synced_frames += copied_frames

    deleted = 0
    for path in delete_paths:
        try:
            path.unlink()
            deleted += 1
        except FileNotFoundError:
            continue

    print(
        f"Copied {copied} new files; "
        f"synced {synced_frames} useful tag frames across {synced_files} files; "
        f"deleted {deleted} duplicates."
    )


if __name__ == "__main__":
    main()
