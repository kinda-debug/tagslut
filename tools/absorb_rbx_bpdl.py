#!/usr/bin/env python3
import argparse
import datetime
import os
import pathlib
import shutil


SRC_ROOT = pathlib.Path("/Volumes/RBX_USB 1/staging/bpdl")
DST_ROOT = pathlib.Path("/Volumes/MUSIC/staging/bpdl")
UNRESOLVED_ROOT = pathlib.Path("/Volumes/RBX_USB 1/DJ_LIBRARY/_UNRESOLVED")


def _is_flac(path: pathlib.Path) -> bool:
    return path.name.lower().endswith(".flac")


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


def _unique_path(target: pathlib.Path) -> pathlib.Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for i in range(1, 10_000):
        candidate = target.with_name(f"{stem}__{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"failed to choose unique path for conflict: {target}")

def _is_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Absorb FLACs from /Volumes/RBX_USB 1/staging/bpdl/ back into /Volumes/MUSIC/staging/bpdl/."
    )
    parser.add_argument("--apply", action="store_true", help="Apply moves (otherwise dry-run).")
    args = parser.parse_args()

    if not SRC_ROOT.exists() or not SRC_ROOT.is_dir():
        print(f"ERROR: source root not found: {SRC_ROOT}")
        return 2

    today = datetime.date.today().strftime("%Y%m%d")
    log_path = DST_ROOT / f"_absorb_log_{today}.txt"
    conflicts_root = DST_ROOT / "_conflicts"

    skipped = 0
    planned: list[tuple[pathlib.Path, pathlib.Path, str]] = []

    for dirpath, _, filenames in os.walk(SRC_ROOT, followlinks=False):
        current = pathlib.Path(dirpath)
        for name in filenames:
            src = current / name
            if not _is_flac(src):
                skipped += 1
                continue
            try:
                if src.is_symlink():
                    skipped += 1
                    continue
            except OSError:
                skipped += 1
                continue
            if _is_under(src, UNRESOLVED_ROOT):
                skipped += 1
                continue
            try:
                rel = src.relative_to(SRC_ROOT)
            except Exception:
                skipped += 1
                continue
            dst = DST_ROOT / rel
            if dst.exists():
                conflict_dst = _unique_path(conflicts_root / rel)
                planned.append((src, conflict_dst, "CONFLICT"))
            else:
                planned.append((src, dst, "MOVE"))

    planned.sort(key=lambda t: str(t[0]))

    moved = 0
    conflicts = 0
    for _, _, kind in planned:
        if kind == "CONFLICT":
            conflicts += 1
        else:
            moved += 1

    for src, dst, kind in planned:
        print(f"{kind}: {src} -> {dst}")

    if args.apply:
        DST_ROOT.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as log:
            for src, dst, kind in planned:
                dst.parent.mkdir(parents=True, exist_ok=True)
                _safe_move(src, dst)
                if not dst.exists():
                    raise RuntimeError(f"destination missing after move: {dst}")
                log.write(f"{kind}: {src} -> {dst}\n")

    print(f"SUMMARY: {moved} moved, {conflicts} conflicts, {skipped} skipped")
    if args.apply:
        print(f"LOG: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
