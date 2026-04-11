#!/usr/bin/env python3
import argparse
import datetime
import os
import pathlib
import re
import shutil


SRC_ROOT = pathlib.Path("/Volumes/MUSIC/mp3_to_sort")
LIB_ROOT = pathlib.Path("/Volumes/MUSIC/MP3_LIBRARY_CLEAN")
LEFTOVERS_ROOT = pathlib.Path("/Volumes/MUSIC/mp3_leftorvers")
INTAKE_ROOT = pathlib.Path("/Volumes/MUSIC/staging/mp3_to_sort_intake")


_TRACK_PREFIX_RE = re.compile(r"^\s*\d+\s*(?:[-_.]\s*\d+)?\s+")


def _norm_basename(name: str) -> str:
    s = _TRACK_PREFIX_RE.sub("", name)
    return s.strip().lower()


def _walk_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for dirpath, _, filenames in os.walk(root, followlinks=False):
        current = pathlib.Path(dirpath)
        for name in filenames:
            p = current / name
            try:
                if p.is_symlink():
                    continue
            except OSError:
                continue
            files.append(p)
    return files


def _safe_move(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(src, dst)
        return
    except OSError as e:
        if getattr(e, "errno", None) != getattr(os, "EXDEV", 18):
            raise

    shutil.copy2(src, dst)
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
    except OSError:
        raise RuntimeError(f"failed to stat after copy: {src} -> {dst}")
    if src_stat.st_size != dst_stat.st_size:
        raise RuntimeError(f"size mismatch after copy: {src} -> {dst}")
    src.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Absorb /Volumes/MUSIC/mp3_to_sort/*.mp3 into staging intake, deduping by normalized basename against library + leftovers (dry-run by default)."
    )
    parser.add_argument("--apply", action="store_true", help="Apply moves (otherwise dry-run report only)")
    args = parser.parse_args()

    if not SRC_ROOT.exists() or not SRC_ROOT.is_dir():
        print(f"ERROR: source not found or not a directory: {SRC_ROOT}")
        return 2
    if not LIB_ROOT.exists() or not LIB_ROOT.is_dir():
        print(f"ERROR: dedupe root not found or not a directory: {LIB_ROOT}")
        return 2
    if not LEFTOVERS_ROOT.exists() or not LEFTOVERS_ROOT.is_dir():
        print(f"ERROR: dedupe root not found or not a directory: {LEFTOVERS_ROOT}")
        return 2

    today = datetime.date.today().strftime("%Y%m%d")
    dupes_root = SRC_ROOT / f"_dupes_{today}"
    log_path = SRC_ROOT / f"_absorb_log_{today}.txt"

    index: dict[str, pathlib.Path] = {}
    for root in (LIB_ROOT, LEFTOVERS_ROOT):
        for p in _walk_files(root):
            if not p.name.lower().endswith(".mp3"):
                continue
            key = _norm_basename(p.name)
            if key and key not in index:
                index[key] = p

    planned = []
    skipped = 0

    for p in sorted(_walk_files(SRC_ROOT), key=str):
        if p.parent != SRC_ROOT:
            skipped += 1
            continue

        if not p.name.lower().endswith(".mp3"):
            skipped += 1
            continue

        key = _norm_basename(p.name)
        match = index.get(key)
        if match is None:
            planned.append((p, INTAKE_ROOT / p.name, "UNIQUE", None))
        else:
            planned.append((p, dupes_root / p.name, "DUPLICATE", match))

    unique_count = 0
    dup_count = 0

    for src, dst, kind, match in planned:
        if kind == "UNIQUE":
            unique_count += 1
            print(f"UNIQUE: {src} -> {dst}")
        else:
            dup_count += 1
            print(f"DUPLICATE: {src} -> {dst} (match: {match})")

    if args.apply:
        INTAKE_ROOT.mkdir(parents=True, exist_ok=True)
        dupes_root.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as log:
            for src, dst, kind, match in planned:
                _safe_move(src, dst)
                if not dst.exists():
                    raise RuntimeError(f"destination missing after move: {dst}")
                if match is None:
                    log.write(f"{kind}: {src} -> {dst}\n")
                else:
                    log.write(f"{kind}: {src} -> {dst} (match: {match})\n")

    print(f"SUMMARY: {unique_count} unique, {dup_count} duplicates, {skipped} skipped")
    if args.apply:
        print(f"LOG: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
