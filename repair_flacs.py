#!/usr/bin/env python3
"""Repair FLAC files.

This script can repair files listed in an M3U playlist or a single file.
It is a thin, safe wrapper around ffmpeg and supports optional per-file
stderr capture for debugging.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
from pathlib import Path
from typing import List, Optional
import hashlib
import re


def parse_args():
    p = argparse.ArgumentParser(description="Repair FLAC files or a single FLAC file")
    g = p.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "playlist",
        nargs="?",
        default="/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u",
        help=(
            "Path to an input M3U playlist "
            "(default: /Volumes/dotad/MUSIC/broken_files_unrepaired.m3u)"
        ),
    )
    g.add_argument("--file", dest="single_file", help="Repair a single FLAC file (path)")
    p.add_argument("--output", "-o", dest="output_dir",
                   default="/Volumes/dotad/MUSIC/REPAIRED",
                   help="Directory where repaired files are written (preserves relative paths)")
    p.add_argument("--no-overwrite-playlist", dest="overwrite_playlist", action="store_false",
                   help="Do not overwrite the input playlist; instead print unrepaired files to stdout")
    p.add_argument("--capture-stderr", dest="capture_stderr", action="store_true",
                   help="Capture ffmpeg stderr to per-file logs under the output/logs directory")
    # Use a lenient decode mode by default to increase chances of salvaging
    # damaged frames. Users can override with --ffmpeg-args.
    p.add_argument("--ffmpeg-args", dest="ffmpeg_args", default="-err_detect ignore_err -c:a flac",
                   help="Extra ffmpeg audio options (default: '-err_detect ignore_err -c:a flac')")
    p.add_argument(
        "--broken-playlist",
        dest="broken_playlist",
        default="/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u",
        help=(
            "Path to an M3U file where unrepaired/corrupt files will be appended. "
            "(default: /Volumes/dotad/MUSIC/broken_files_unrepaired.m3u)"
        ),
    )
    return p.parse_args()


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def run_repair(src: Path, dst: Path, ffmpeg_args: str, capture_stderr: bool, logs_dir: Path) -> bool:
    ensure_parent(dst)
    cmd: List[str] = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src)]
    if ffmpeg_args:
        cmd.extend(shlex.split(ffmpeg_args))
    cmd.append(str(dst))

    stderr_fp = subprocess.DEVNULL
    if capture_stderr:
        logs_dir.mkdir(parents=True, exist_ok=True)
        # Create a filesystem-safe, reasonably short log filename. Some
        # file paths (especially long artist/album/title combos) can exceed
        # the OS per-component filename limit and cause OSError (Errno 63).
        # To avoid that we sanitize the dst.name and append a short hash.
        base = dst.name
        # Replace problematic chars with underscore
        safe_base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
        # Trim to a safe length and append a short hex of the full path
        short = safe_base[:80]
        h = hashlib.sha1(dst.as_posix().encode("utf-8")).hexdigest()[:8]
        log_name = f"{short}_{h}.stderr.log"
        log_path = logs_dir / log_name
        stderr_fp = open(log_path, "wb")

    # Print the actual ffmpeg command we will run (with full paths) so the
    # exact invocation is visible in logs and reproductions.
    try:
        try:
            printable = shlex.join(cmd)
        except Exception:
            printable = " ".join(cmd)
        print(f"Running: {printable}")
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=stderr_fp)
        ok = (result.returncode == 0 and dst.is_file())
    finally:
        # close file handle if we opened one
        if capture_stderr and hasattr(stderr_fp, "close") and stderr_fp is not subprocess.DEVNULL:
            stderr_fp.close()

    return ok


def repair_playlist(playlist: Path, output_dir: Path, ffmpeg_args: str, capture_stderr: bool, overwrite: bool,
                   broken_playlist: Optional[Path] = None) -> int:
    if not playlist.is_file():
        print(f"Playlist not found: {playlist}")
        return 2

    logs_dir = output_dir / "logs"
    with playlist.open("r") as f:
        files = [line.strip() for line in f if line.strip() and Path(line.strip()).is_file()]

    total = len(files)
    unrepaired: List[str] = []

    for idx, src in enumerate(files, 1):
        src_path = Path(src)
        if src_path.is_absolute():
            try:
                rel_path = src_path.relative_to("/Volumes/dotad/MUSIC")
            except Exception:
                rel_path = Path(src_path.name)
        else:
            rel_path = Path(src_path.name)
        dst = output_dir.joinpath(rel_path)
        if dst.is_file():
            print(f"[{idx}/{total}] Already repaired: {dst}")
            continue
        print(f"[{idx}/{total}] Repairing: {src} -> {dst}")
        ok = run_repair(src_path, dst, ffmpeg_args, capture_stderr, logs_dir)
        if not ok:
            print(f"  Failed: {src}")
            unrepaired.append(src)

    # If a broken_playlist is provided, append unrepaired paths there.
    if broken_playlist:
        broken_playlist = Path(broken_playlist)
        broken_playlist.parent.mkdir(parents=True, exist_ok=True)
        with broken_playlist.open("a") as bp:
            for p in unrepaired:
                bp.write(p + "\n")
        print(f"Repair complete. {total - len(unrepaired)} files repaired; {len(unrepaired)} appended to {broken_playlist}.")
    else:
        if overwrite:
            with playlist.open("w") as fout:
                for path in unrepaired:
                    fout.write(path + "\n")
            print(
                f"Repair complete. {total - len(unrepaired)} files repaired, "
                f"{len(unrepaired)} remain in {playlist}."
            )
        else:
            if unrepaired:
                print("Unrepaired files:")
                for p in unrepaired:
                    print(p)
            else:
                print("All files repaired.")

    return 0


def repair_single(path: Path, output_dir: Path, ffmpeg_args: str, capture_stderr: bool,
                  broken_playlist: Optional[Path] = None) -> int:
    src = Path(path)
    if not src.is_file():
        print(f"File not found: {src}")
        return 2

    if src.is_absolute():
        try:
            rel_path = src.relative_to("/Volumes/dotad/MUSIC")
        except Exception:
            rel_path = Path(src.name)
    else:
        rel_path = Path(src.name)
    dst = Path(output_dir).joinpath(rel_path)
    logs_dir = Path(output_dir) / "logs"
    print(f"Repairing single file: {src} -> {dst}")
    ok = run_repair(src, dst, ffmpeg_args, capture_stderr, logs_dir)
    if not ok:
        print(f"Repair failed: {src}")
        if broken_playlist:
            bp = Path(broken_playlist)
            bp.parent.mkdir(parents=True, exist_ok=True)
            with bp.open("a") as f:
                f.write(str(src) + "\n")
            print(f"Appended failed file to {bp}")
        return 1
    print(f"Repaired: {dst}")
    return 0


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if getattr(args, "single_file", None):
        return repair_single(
            args.single_file,
            output_dir,
            args.ffmpeg_args,
            args.capture_stderr,
            Path(args.broken_playlist) if args.broken_playlist else None,
        )

    return repair_playlist(
        Path(args.playlist),
        output_dir,
        args.ffmpeg_args,
        args.capture_stderr,
        args.overwrite_playlist,
        Path(args.broken_playlist) if args.broken_playlist else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
    