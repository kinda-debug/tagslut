#!/usr/bin/env python3
"""resolve_lossless_winner.py

Per-stem lossless winner selection for SpotiFLACnext staging directories.

Rules (in priority order):
  1. m4a + mp3 coexisting for the same stem → m4a is lossless (always).
  2. eac3 codec → not lossless regardless of container; flag NO_LOSSLESS.
  3. ALAC m4a only → transcode to FLAC in-place, delete m4a.
  4. FLAC only → keep, delete any lossy m4a for same stem.
  5. Both FLAC and ALAC m4a → larger file is the better source.
     ALAC larger: transcode ALAC→FLAC, delete original FLAC and m4a.
     FLAC larger: keep FLAC, delete m4a.
  6. MP3s are never deleted by this script.

Output (stdout): TSV  ACTION<tab>PATH
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path


LOSSLESS_CODECS = {"alac", "flac"}
LOSSY_SKIP_CODECS = {"eac3", "ac3", "dts", "aac", "mp3"}


def probe_codec(path: Path) -> str:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=nk=1:nw=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip().split("\n")[0].strip() or "unknown"
    except Exception:
        return "unknown"


def transcode_alac_to_flac(src: Path, dest: Path) -> bool:
    tmp = dest.parent / f".tmp.{dest.name}"
    try:
        # Try with video stream (cover art) first
        r = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-nostdin", "-y",
                "-i", str(src),
                "-map_metadata", "0", "-map", "0:a:0", "-map", "0:v?",
                "-c:a", "flac", "-compression_level", "12", "-c:v", "copy",
                str(tmp),
            ],
            capture_output=True, timeout=300,
        )
        if r.returncode != 0:
            # Fallback: audio only
            subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-nostdin", "-y",
                    "-i", str(src),
                    "-map_metadata", "0", "-map", "0:a:0",
                    "-c:a", "flac", "-compression_level", "12",
                    str(tmp),
                ],
                capture_output=False, check=True, timeout=300,
            )
        tmp.rename(dest)
        return True
    except Exception as e:
        print(f"ERROR\ttranscode failed: {src}: {e}", flush=True)
        tmp.unlink(missing_ok=True)
        return False


def collect_files(paths: list[Path]) -> dict[tuple[Path, str], list[Path]]:
    """Group files by (directory, stem). Returns ordered dict."""
    groups: dict[tuple[Path, str], list[Path]] = defaultdict(list)
    for p in paths:
        if p.is_file():
            groups[(p.parent, p.stem)].append(p)
    return groups


def process_group(
    stem_key: tuple[Path, str],
    files: list[Path],
    codecs: dict[Path, str],
    dry_run: bool,
    overwrite: bool,
) -> tuple[str, int, int, int]:
    """
    Returns (log_lines_str, transcoded, kept, flagged).
    Prints TSV lines to stdout.
    """
    flac: list[Path] = []
    alac: list[Path] = []
    eac3_aac: list[Path] = []
    mp3: list[Path] = []

    has_mp3 = any(f.suffix.lower() == ".mp3" for f in files)

    for f in files:
        ext = f.suffix.lower()
        codec = codecs[f]
        if ext == ".flac":
            flac.append(f)
        elif ext == ".mp3":
            mp3.append(f)
        elif ext == ".m4a":
            if codec in LOSSLESS_CODECS:
                alac.append(f)
            else:
                eac3_aac.append(f)

    transcoded = kept = flagged = 0

    def emit(action: str, path: Path, note: str = "") -> None:
        msg = f"{action}\t{path}"
        if note:
            msg += f"  ({note})"
        print(msg, flush=True)

    def do_rm(f: Path, action: str = "DELETE") -> None:
        emit(action, f)
        if not dry_run:
            f.unlink(missing_ok=True)

    # No lossless at all
    if not flac and not alac:
        for f in eac3_aac:
            emit("NO_LOSSLESS", f)
        for f in mp3:
            emit("NO_LOSSLESS_KEEP_MP3", f)
        return "", 0, 0, 1

    # Pick best candidates by size
    best_alac = max(alac, key=lambda f: f.stat().st_size) if alac else None
    best_flac = max(flac, key=lambda f: f.stat().st_size) if flac else None

    # FLAC only
    if best_flac and not best_alac:
        emit("KEEP_FLAC", best_flac)
        for f in flac:
            if f != best_flac:
                do_rm(f, "DELETE_INFERIOR_FLAC")
        for f in eac3_aac:
            do_rm(f, "DELETE_LOSSY_M4A")
        return "", 0, 1, 0

    # ALAC only
    if best_alac and not best_flac:
        dest = best_alac.parent / (best_alac.stem + ".flac")
        if dest.exists() and not overwrite:
            emit("SKIP_EXISTS", dest)
            kept += 1
        else:
            emit("TRANSCODE_ALAC", best_alac, f"-> {dest.name}")
            if not dry_run:
                if transcode_alac_to_flac(best_alac, dest):
                    best_alac.unlink(missing_ok=True)
                    transcoded += 1
                else:
                    return "", 0, 0, 0  # error already printed
        for f in alac:
            if f != best_alac:
                do_rm(f, "DELETE_INFERIOR_ALAC")
        for f in eac3_aac:
            do_rm(f, "DELETE_LOSSY_M4A")
        return "", transcoded, kept, 0

    # Both present — larger wins
    alac_size = best_alac.stat().st_size  # type: ignore[union-attr]
    flac_size = best_flac.stat().st_size  # type: ignore[union-attr]

    if alac_size >= flac_size:
        dest = best_alac.parent / (best_alac.stem + ".flac")  # type: ignore[union-attr]
        tmp_dest = best_alac.parent / (best_alac.stem + ".__winner__.flac")  # type: ignore[union-attr]
        emit("WIN_ALAC_LARGER", best_alac,  # type: ignore[arg-type]
             f"ALAC {alac_size}B >= FLAC {flac_size}B -> {dest.name}")
        if not dry_run:
            if transcode_alac_to_flac(best_alac, tmp_dest):  # type: ignore[arg-type]
                for f in flac:
                    f.unlink(missing_ok=True)
                tmp_dest.rename(dest)
                best_alac.unlink(missing_ok=True)  # type: ignore[union-attr]
                for f in alac:
                    if f != best_alac:
                        f.unlink(missing_ok=True)
                transcoded += 1
            else:
                tmp_dest.unlink(missing_ok=True)
    else:
        emit("WIN_FLAC_LARGER", best_flac,  # type: ignore[arg-type]
             f"FLAC {flac_size}B > ALAC {alac_size}B")
        kept += 1
        if not dry_run:
            for f in alac:
                f.unlink(missing_ok=True)
            for f in flac:
                if f != best_flac:
                    f.unlink(missing_ok=True)
        else:
            for f in alac:
                do_rm(f, "DELETE_INFERIOR_ALAC")
            for f in flac:
                if f != best_flac:
                    do_rm(f, "DELETE_INFERIOR_FLAC")
        for f in eac3_aac:
            do_rm(f, "DELETE_LOSSY_M4A")

    return "", transcoded, kept, 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve lossless winner per stem in SpotiFLACnext staging."
    )
    parser.add_argument("--scan-path", metavar="DIR",
                        help="Recursively scan DIR for audio files.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print actions, make no changes.")
    parser.add_argument("--overwrite", action="store_true",
                        help="Re-transcode even if output FLAC already exists.")
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="Individual files to process.")
    args = parser.parse_args()

    paths: list[Path] = []

    if args.scan_path:
        root = Path(args.scan_path).expanduser().resolve()
        if not root.is_dir():
            print(f"error: not a directory: {root}", file=sys.stderr)
            sys.exit(1)
        for ext in ("*.flac", "*.m4a", "*.mp3"):
            paths.extend(sorted(root.rglob(ext)))
        paths = [p for p in paths if not p.name.startswith("._")]

    for f in args.files:
        p = Path(f).expanduser().resolve()
        if p.is_file():
            paths.append(p)

    if not paths:
        print("error: no input files found", file=sys.stderr)
        parser.print_usage(sys.stderr)
        sys.exit(1)

    # Probe all files upfront
    print(f"probing {len(paths)} files...", file=sys.stderr)
    codecs: dict[Path, str] = {}
    for p in paths:
        codecs[p] = probe_codec(p)

    groups = collect_files(paths)

    total_transcoded = total_kept = total_flagged = 0

    for key, files in sorted(groups.items()):
        _, t, k, f = process_group(key, files, codecs, args.dry_run, args.overwrite)
        total_transcoded += t
        total_kept += k
        total_flagged += f

    print("---", file=sys.stderr)
    print(
        f"transcoded: {total_transcoded}  kept: {total_kept}"
        f"  flagged_no_lossless: {total_flagged}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
