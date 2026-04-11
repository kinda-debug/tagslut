#!/usr/bin/env python3
import argparse
import datetime
import os
import pathlib
import re
import shutil


TRACK_PREFIX_RE = re.compile(r"^\s*\d{1,3}(?:-\d{1,3})?[\s._-]+")


def _decode_fs(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


def _normalize_basename_stem(stem: str) -> str:
    s = stem.strip()
    s = TRACK_PREFIX_RE.sub("", s)
    return s.strip().casefold()


def _build_mp3_index(root: bytes) -> dict[str, bytes]:
    index: dict[str, bytes] = {}
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.lower().endswith(b".mp3"):
                continue
            stem = _decode_fs(name)[:-4]
            key = _normalize_basename_stem(stem)
            if key and key not in index:
                index[key] = os.path.join(dirpath, name)
    return index


def _pick_non_overwriting_dest(dst_dir: bytes, filename: bytes) -> bytes:
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dst_dir, filename)
    if not os.path.exists(candidate):
        return candidate
    for i in range(1, 10_000):
        candidate = os.path.join(dst_dir, base + f" ({i})".encode("utf-8") + ext)
        if not os.path.exists(candidate):
            return candidate
    raise RuntimeError(f"Unable to find non-colliding destination for {_decode_fs(filename)}")

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Absorb /Volumes/MUSIC/mp3_to_sort into intake with basename-only dedup check."
    )
    parser.add_argument("--apply", action="store_true", help="Execute moves (default: dry-run).")
    args = parser.parse_args()

    today = datetime.datetime.now().strftime("%Y%m%d")
    src_dir = pathlib.Path("/Volumes/MUSIC/mp3_to_sort")
    clean_dir = pathlib.Path("/Volumes/MUSIC/MP3_LIBRARY_CLEAN")
    leftovers_dir = pathlib.Path("/Volumes/MUSIC/mp3_leftorvers")
    intake_dir = pathlib.Path("/Volumes/MUSIC/mdl/mp3_to_sort_intake")
    log_path = src_dir / f"_absorb_log_{today}.txt"
    dupes_dir = src_dir / f"_dupes_{today}"

    src_b = os.fsencode(str(src_dir))
    clean_b = os.fsencode(str(clean_dir))
    leftovers_b = os.fsencode(str(leftovers_dir))
    intake_b = os.fsencode(str(intake_dir))
    dupes_b = os.fsencode(str(dupes_dir))

    clean_index = _build_mp3_index(clean_b)
    leftovers_index = _build_mp3_index(leftovers_b)

    if args.apply:
        os.makedirs(intake_b, exist_ok=True)

    unique_count = dup_count = 0
    with open(log_path, "a", encoding="utf-8") as log:
        log.write(f"{today} {'APPLY' if args.apply else 'DRYRUN'}\n")
        for entry in os.scandir(src_b):
            if not entry.is_file():
                continue
            name = entry.name
            if not name.lower().endswith(b".mp3"):
                continue
            stem = _decode_fs(name)[:-4]
            key = _normalize_basename_stem(stem)
            src_path = entry.path
            match = clean_index.get(key) or leftovers_index.get(key)
            if match is not None:
                dup_count += 1
                planned = _pick_non_overwriting_dest(dupes_b, name) if args.apply else os.path.join(dupes_b, name)
                print(f"DUPLICATE: {_decode_fs(src_path)} -> {_decode_fs(planned)} (match: {_decode_fs(match)})")
                log.write(f"DUPLICATE\t{_decode_fs(src_path)}\t{_decode_fs(planned)}\tMATCH\t{_decode_fs(match)}\n")
                if args.apply:
                    os.makedirs(dupes_b, exist_ok=True)
                    shutil.move(src_path, planned)
                    if not os.path.exists(planned):
                        raise RuntimeError(f"Move failed: {_decode_fs(planned)}")
                continue
            unique_count += 1
            planned = _pick_non_overwriting_dest(intake_b, name) if args.apply else os.path.join(intake_b, name)
            print(f"UNIQUE: {_decode_fs(src_path)} -> {_decode_fs(planned)}")
            log.write(f"UNIQUE\t{_decode_fs(src_path)}\t{_decode_fs(planned)}\n")
            if args.apply:
                shutil.move(src_path, planned)
                if not os.path.exists(planned):
                    raise RuntimeError(f"Move failed: {_decode_fs(planned)}")
        log.write(f"SUMMARY\tunique={unique_count}\tduplicates={dup_count}\n")

    print(f"Summary: {unique_count} unique (moved to intake), {dup_count} duplicates (archived).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
