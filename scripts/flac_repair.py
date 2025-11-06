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
import datetime as _dt
from dataclasses import dataclass
import contextlib
from pathlib import Path
from typing import Iterable, Optional, Tuple, Iterator
import hashlib
import re
import shutil
import tempfile
import os
import signal
import time
import sys

# Import formatting settings from the canonical common module
import pathlib

# Ensure repo root is on sys.path when running this file directly so package
# imports like `from scripts.lib import common` succeed.
if __package__ is None:  # pragma: no cover - only for direct script runs
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

from scripts.lib import common as flac_scan


def log(message: str) -> None:
    """Print a human friendly timestamped log message."""

    timestamp = _dt.datetime.now().strftime("%H:%M:%S")

    # Colorize paths in the message
    if ": " in message:
        prefix, rest = message.split(": ", 1)
        if "/" in rest or "\\" in rest:  # detect path
            rest = flac_scan.colorize_path(rest.strip())
            message = f"{prefix}: {rest}"

    # Rotate the timestamp color using the shared index in flac_scan
    timestamp_color = flac_scan.gay_flag_colors[flac_scan.timestamp_color_index % 6]
    flac_scan.timestamp_color_index += 1
    flac_scan.last_timestamp_color = timestamp_color

    message_color = ""
    if "Progress" in message:
        # Color only the number in rainbow
        parts = message.split()
        if len(parts) >= 2:
            number = parts[1]
            color = flac_scan.gay_flag_colors[flac_scan.progress_word_offset % 6]
            flac_scan.progress_word_offset += 1
            parts[1] = f"{color}{number}\033[0m"
            message = " ".join(parts)
            # Make percentage bold (white bold)
            try:
                message = re.sub(r"\(([^)]*%)\)", r"(\033[1;37m\1\033[0m)", message)
            except re.error:
                pass
    elif "cached metadata" in message:
        message_color = "\033[35m"  # magenta for cached skips
    elif "Added broken file to playlist" in message:
        message_color = "\033[35m"  # magenta for added to playlist
    elif "WARNING" in message or "Error" in message or "freeze" in message.lower():
        message_color = "\033[33m"  # yellow for warnings/errors
    elif (
        "Skipping" in message or "broken" in message or "quarantine" in message.lower()
    ):
        message_color = "\033[31m"  # red for skips/broken
    elif "Repaired" in message:
        # Successful repair -> green
        message_color = "\033[32m"
    elif (
        "Failed" in message
        or "Failure" in message
        or message.strip().startswith("Failed:")
    ):
        # Failed repair -> red
        message_color = "\033[31m"
    elif "Processed" in message or "completed" in message or "Killed" in message:
        if ": " in message:
            prefix, rest = message.split(": ", 1)
            # Color prefix green, rest lighter grey (white)
            print(
                f"{timestamp_color}[{timestamp}]\033[0m \033[32m{prefix}:\033[0m \033[37m{rest}\033[0m"
            )
            return
        else:
            message_color = "\033[32m"  # green for success

    print(f"{timestamp_color}[{timestamp}]\033[0m {message_color}{message}\033[0m")


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
    g.add_argument(
        "--file", dest="single_file", help="Repair a single FLAC file (path)"
    )
    p.add_argument(
        "--output",
        "-o",
        dest="output_dir",
        default="/Volumes/dotad/MUSIC/REPAIRED",
        help="Directory where repaired files are written (preserves relative paths)",
    )
    p.add_argument(
        "--no-overwrite-playlist",
        dest="overwrite_playlist",
        action="store_false",
        help="Do not overwrite the input playlist; instead print unrepaired files to stdout",
    )
    p.add_argument(
        "--capture-stderr",
        dest="capture_stderr",
        action="store_true",
        help="Capture ffmpeg stderr to per-file logs under the output/logs directory",
    )
    # Use a lenient decode mode by default to increase chances of salvaging
    # damaged frames. Users can override with --ffmpeg-args.
    p.add_argument(
        "--ffmpeg-args",
        dest="ffmpeg_args",
        default="-err_detect ignore_err -c:a flac",
        help="Extra ffmpeg audio options (default: '-err_detect ignore_err -c:a flac')",
    )
    p.add_argument(
        "--broken-playlist",
        dest="broken_playlist",
        default="/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u",
        help=(
            "Path to an M3U file where unrepaired/corrupt files will be appended. "
            "(default: /Volumes/dotad/MUSIC/broken_files_unrepaired.m3u)"
        ),
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting destination files (creates a backup first)",
    )
    p.add_argument(
        "--backup-dir",
        dest="backup_dir",
        help="Directory for storing backups when --overwrite is used",
    )
    p.add_argument(
        "--trim-seconds",
        type=float,
        default=10.0,
        help="Seconds to trim from the tail during the final fallback step (default: 10)",
    )
    p.add_argument(
        "--ffmpeg-timeout",
        type=int,
        default=30,
        help="Seconds allowed for each ffmpeg step before forcibly killing it (default: 30)",
    )
    p.add_argument(
        "--temp-dir",
        dest="temp_dir",
        help="Optional directory for intermediate WAV files",
    )
    p.set_defaults(enable_transcode=True, enable_reencode=True, enable_trim=True)
    p.add_argument(
        "--disable-transcode",
        dest="enable_transcode",
        action="store_false",
        help="Skip the initial lenient transcode step",
    )
    p.add_argument(
        "--disable-reencode",
        dest="enable_reencode",
        action="store_false",
        help="Skip the WAV re-encode fallback step",
    )
    p.add_argument(
        "--disable-trim",
        dest="enable_trim",
        action="store_false",
        help="Skip the tail-trimming fallback step",
    )
    return p.parse_args()


@dataclass
class PipelineOptions:
    """Configuration for the automated FLAC repair pipeline."""

    ffmpeg_args: str
    overwrite: bool
    backup_dir: Optional[Path]
    ffmpeg_timeout: int
    enable_transcode: bool
    enable_reencode: bool
    enable_trim: bool
    trim_seconds: float
    temp_dir: Optional[Path]


def ensure_parent(path: Path) -> None:
    """Ensure the destination directory exists."""

    path.parent.mkdir(parents=True, exist_ok=True)


def _sanitize_component(name: str) -> str:
    """Return a filesystem-safe string derived from *name*."""

    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return safe[:80] or "file"


def _stderr_log_path(logs_dir: Path, dst: Path, step: str) -> Path:
    """Compute a unique stderr log path for *dst* and *step*."""

    safe_step = _sanitize_component(step)[:16]
    safe_base = _sanitize_component(dst.stem or dst.name)
    digest_input = f"{dst.as_posix()}::{step}".encode("utf-8")
    digest = hashlib.sha1(digest_input).hexdigest()[:8]
    return logs_dir / f"{safe_base}_{safe_step}_{digest}.stderr.log"


def _run_ffmpeg_step(
    cmd: Iterable[str], step: str, log_path: Optional[Path]
) -> Tuple[bool, str]:
    """Execute *cmd* via ``ffmpeg`` and optionally persist stderr.

    This helper will attempt a conservative retry on failure (insert
    ``-threads 1`` and strip ``-err_detect``) to work around decoder
    crashes in libavcodec for problematic files.
    """
    base_command = list(cmd)
    timeout: int = getattr(_run_ffmpeg_step, "_default_timeout", 30)

    def _invoke(
        command: list[str],
    ) -> Tuple[subprocess.Popen | None, Optional[int], str]:
        """Start the command, wait with timeout handling, and return (process, returncode, stderr_text).

        If ffmpeg is not found returns (None, None, "ffmpeg not found")."""
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError:
            return None, None, "ffmpeg not found"

        pgid = None
        stderr_text = ""
        try:
            try:
                pgid = os.getpgid(process.pid)
                try:
                    flac_scan.register_active_pgid(pgid)
                except OSError:
                    pass
            except OSError:
                pgid = None

            try:
                stderr_bytes, _ = process.communicate(timeout=timeout)
                stderr_text = (
                    stderr_bytes.decode("utf-8", "replace") if stderr_bytes else ""
                )
            except subprocess.TimeoutExpired:
                # Graceful then forceful termination of the process group
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except OSError:
                    try:
                        process.kill()
                    except OSError:
                        pass
                t0 = time.time()
                while True:
                    if process.poll() is not None:
                        break
                    if time.time() - t0 > 2.0:
                        break
                    time.sleep(0.1)
                if process.poll() is None:
                    try:
                        pgid = os.getpgid(process.pid)
                        os.killpg(pgid, signal.SIGKILL)
                    except OSError:
                        try:
                            process.kill()
                        except OSError:
                            pass
                try:
                    stderr_bytes, _ = process.communicate(timeout=5)
                    stderr_text = (
                        stderr_bytes.decode("utf-8", "replace") if stderr_bytes else ""
                    )
                except (subprocess.SubprocessError, OSError, UnicodeDecodeError):
                    stderr_text = ""

            return process, process.returncode, stderr_text
        finally:
            try:
                if pgid is not None:
                    try:
                        flac_scan.unregister_active_pgid(pgid)
                    except OSError:
                        pass
            except OSError:
                pass

    # Try up to two attempts: initial, then a conservative retry.
    attempts = 2
    last_stderr = ""
    for attempt in range(1, attempts + 1):
        command = base_command.copy()
        if attempt == 2:
            # Build a conservative fallback command: remove -err_detect and add -threads 1
            cons: list[str] = []
            skip_next = False
            for i, token in enumerate(command):
                if skip_next:
                    skip_next = False
                    continue
                if token == "-err_detect":
                    # skip this token and its following value if present
                    skip_next = True
                    continue
                cons.append(token)
            command = cons
            if "-threads" not in command:
                # insert after the 'ffmpeg' literal (index 0)
                if len(command) >= 1 and command[0].endswith("ffmpeg"):
                    command.insert(1, "-threads")
                    command.insert(2, "1")
                else:
                    # safe fallback: prepend threads
                    command = ["ffmpeg", "-threads", "1"] + command[1:]

        proc, returncode, stderr_text = _invoke(command)
        if proc is None:
            return False, stderr_text

        last_stderr = stderr_text or last_stderr
        # Persist per-attempt logs if requested (suffix attempt number)
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            attempt_log = (
                log_path.with_name(
                    log_path.stem + f"_attempt{attempt}" + log_path.suffix
                )
                if log_path.suffix
                else log_path.with_name(log_path.name + f"_attempt{attempt}")
            )
            with attempt_log.open("w", encoding="utf-8") as handle:
                handle.write(stderr_text)

        success = returncode == 0
        if success:
            return True, stderr_text
        # if failed and this was the first attempt, continue to retry
    return False, last_stderr


def _cleanup_partial(path: Path) -> None:
    """Remove partially written files without raising."""

    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def create_backup(source: Path, backup_dir: Optional[Path]) -> Optional[Path]:
    """Create a timestamped backup of *source* in *backup_dir*."""

    target_dir = Path(backup_dir).expanduser() if backup_dir else source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = source.suffix or ".flac"
    backup = target_dir / f"{source.stem}_{timestamp}{suffix}.bak"
    counter = 1
    while backup.exists():
        backup = target_dir / f"{source.stem}_{timestamp}_{counter}{suffix}.bak"
        counter += 1
    shutil.copy2(source, backup)
    print(f"Created backup: {backup}")
    return backup


@contextlib.contextmanager
def temporary_directory(base: Optional[Path]) -> Iterator[Path]:
    """Yield a temporary directory, honouring an optional *base* path."""

    if base:
        base_path = Path(base).expanduser()
        base_path.mkdir(parents=True, exist_ok=True)
        temp_path = Path(tempfile.mkdtemp(prefix="repair_", dir=str(base_path)))
        try:
            yield temp_path
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)
    else:
        with tempfile.TemporaryDirectory(prefix="repair_") as temp:
            yield Path(temp)


def lenient_transcode(
    src: Path,
    dst: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    logs_dir: Path,
) -> bool:
    """Attempt a direct lenient transcode to FLAC."""

    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src)]
    if options.ffmpeg_args:
        cmd.extend(shlex.split(options.ffmpeg_args))
    cmd.append(str(dst))
    log_path = _stderr_log_path(logs_dir, dst, "transcode") if capture_stderr else None
    # configure helper default timeout for this invocation
    setattr(_run_ffmpeg_step, "_default_timeout", options.ffmpeg_timeout)
    success, _ = _run_ffmpeg_step(cmd, "transcode", log_path)
    if success and dst.exists():
        return True
    _cleanup_partial(dst)
    return False


def decode_and_reencode(
    src: Path,
    dst: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    logs_dir: Path,
) -> bool:
    """Decode to WAV then re-encode to FLAC, enforcing size sanity checks."""

    with temporary_directory(options.temp_dir) as temp_dir:
        wav_path = temp_dir / f"{dst.stem}_repair.wav"
        decode_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(src),
            str(wav_path),
        ]
        decode_log = (
            _stderr_log_path(logs_dir, dst, "decode") if capture_stderr else None
        )
        setattr(_run_ffmpeg_step, "_default_timeout", options.ffmpeg_timeout)
        success, _ = _run_ffmpeg_step(decode_cmd, "decode", decode_log)
        if not success or not wav_path.exists():
            _cleanup_partial(dst)
            return False

        encode_cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-y",
            "-i",
            str(wav_path),
            "-c:a",
            "flac",
            str(dst),
        ]
        encode_log = (
            _stderr_log_path(logs_dir, dst, "reencode") if capture_stderr else None
        )
        setattr(_run_ffmpeg_step, "_default_timeout", options.ffmpeg_timeout)
        success, _ = _run_ffmpeg_step(encode_cmd, "reencode", encode_log)
        if not success or not dst.exists():
            _cleanup_partial(dst)
            return False

    try:
        src_size = src.stat().st_size
        dst_size = dst.stat().st_size
    except OSError:
        _cleanup_partial(dst)
        return False

    max_allowed = max(src_size * 2, src_size + 1_048_576)
    if dst_size <= 0 or dst_size > max_allowed:
        print(f"Size check failed: output {dst_size} bytes vs source {src_size} bytes")
        _cleanup_partial(dst)
        return False
    return True


def trim_and_reencode(
    src: Path,
    dst: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    logs_dir: Path,
) -> bool:
    """Trim the tail of the file and attempt a re-encode."""

    if options.trim_seconds <= 0:
        print("Trim seconds <= 0; skipping trim fallback.")
        return False
    filter_arg = f"atrim=end=-{options.trim_seconds:.3f}"
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(src),
        "-af",
        filter_arg,
        "-c:a",
        "flac",
        str(dst),
    ]
    log_path = _stderr_log_path(logs_dir, dst, "trim") if capture_stderr else None
    setattr(_run_ffmpeg_step, "_default_timeout", options.ffmpeg_timeout)
    success, _ = _run_ffmpeg_step(cmd, "trim", log_path)
    if not success or not dst.exists():
        _cleanup_partial(dst)
        return False
    try:
        dst_size = dst.stat().st_size
        src_size = src.stat().st_size
    except OSError:
        _cleanup_partial(dst)
        return False
    if dst_size <= 0 or dst_size > src_size:
        print("Trimmed output failed sanity checks; discarding result.")
        _cleanup_partial(dst)
        return False
    return True


def execute_pipeline(
    src: Path,
    dst: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    logs_dir: Path,
) -> bool:
    """Run the configured repair pipeline for a single file."""

    ensure_parent(dst)
    if capture_stderr:
        logs_dir.mkdir(parents=True, exist_ok=True)

    backup_path: Optional[Path] = None
    if dst.exists():
        if not options.overwrite:
            print(f"Destination exists; use --overwrite to replace {dst}")
            return False
        backup_path = create_backup(dst, options.backup_dir)
    elif options.overwrite and src.resolve() == dst.resolve():
        backup_path = create_backup(src, options.backup_dir)

    success = False
    try:
        if options.enable_transcode:
            success = lenient_transcode(src, dst, options, capture_stderr, logs_dir)
            if success:
                return True
        if options.enable_reencode:
            success = decode_and_reencode(src, dst, options, capture_stderr, logs_dir)
            if success:
                return True
        if options.enable_trim:
            success = trim_and_reencode(src, dst, options, capture_stderr, logs_dir)
            if success:
                return True
        return False
    finally:
        if not success and backup_path is not None and backup_path.exists():
            try:
                shutil.copy2(backup_path, dst)
                print(f"Restored original from backup {backup_path}")
            except OSError as exc:
                print(f"Failed to restore backup {backup_path}: {exc}")


def build_options(args: argparse.Namespace) -> PipelineOptions:
    """Construct :class:`PipelineOptions` from parsed arguments."""

    backup_dir = Path(args.backup_dir).expanduser() if args.backup_dir else None
    temp_dir = Path(args.temp_dir).expanduser() if args.temp_dir else None
    return PipelineOptions(
        ffmpeg_args=args.ffmpeg_args,
        overwrite=bool(args.overwrite),
        backup_dir=backup_dir,
        ffmpeg_timeout=int(args.ffmpeg_timeout),
        enable_transcode=bool(args.enable_transcode),
        enable_reencode=bool(args.enable_reencode),
        enable_trim=bool(args.enable_trim),
        trim_seconds=max(0.0, float(args.trim_seconds)),
        temp_dir=temp_dir,
    )


def resolve_relative_output(src: Path, output_dir: Path) -> Path:
    """Map *src* into *output_dir*, preserving structure when possible."""

    if src.is_absolute():
        try:
            rel_path = src.relative_to("/Volumes/dotad/MUSIC")
        except ValueError:
            rel_path = Path(src.name)
    else:
        rel_path = Path(src.name)
    return output_dir.joinpath(rel_path)


def repair_playlist(
    playlist: Path,
    output_dir: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    overwrite_playlist: bool,
    broken_playlist: Optional[Path] = None,
) -> int:
    """Repair all files listed in *playlist* using the configured pipeline."""

    if not playlist.is_file():
        print(f"Playlist not found: {playlist}")
        return 2

    logs_dir = output_dir / "logs"
    with playlist.open("r", encoding="utf-8") as handle:
        files = [
            line.strip()
            for line in handle
            if line.strip() and Path(line.strip()).is_file()
        ]

    total = len(files)
    unrepaired: list[str] = []

    for idx, src in enumerate(files, 1):
        src_path = Path(src)
        dst = resolve_relative_output(src_path, output_dir)
        if dst.is_file() and not options.overwrite:
            continue
        percent = (idx / total * 100.0) if total else 0.0
        log(f"Progress: {idx}/{total} ({percent:.1f}%)")
        ok = execute_pipeline(src_path, dst, options, capture_stderr, logs_dir)
        if not ok:
            log(f"  Failed: {src_path.name}")
            unrepaired.append(src)
        else:
            log(f"  Repaired: {dst.name}")

    if broken_playlist:
        broken_playlist.parent.mkdir(parents=True, exist_ok=True)
        with broken_playlist.open("a", encoding="utf-8") as bp:
            for entry in unrepaired:
                bp.write(entry + "\n")
        print(
            f"Repair complete. {total - len(unrepaired)} files repaired; "
            f"{len(unrepaired)} appended to {broken_playlist}."
        )
    else:
        if overwrite_playlist:
            with playlist.open("w", encoding="utf-8") as fout:
                for entry in unrepaired:
                    fout.write(entry + "\n")
            print(
                f"Repair complete. {total - len(unrepaired)} files repaired, "
                f"{len(unrepaired)} remain in {playlist}."
            )
        elif unrepaired:
            print("Unrepaired files:")
            for entry in unrepaired:
                print(entry)
        else:
            print("All files repaired.")

    return 0


def repair_single(
    path: Path,
    output_dir: Path,
    options: PipelineOptions,
    capture_stderr: bool,
    broken_playlist: Optional[Path] = None,
) -> int:
    """Repair a single file at *path* and write the result under *output_dir*."""

    src = Path(path)
    if not src.is_file():
        print(f"File not found: {src}")
        return 2

    dst = resolve_relative_output(src, output_dir)
    if dst.is_file() and not options.overwrite:
        print(f"Already repaired: {dst}")
        return 0
    logs_dir = output_dir / "logs"
    print(f"Repairing single file: {src} -> {dst}")
    ok = execute_pipeline(src, dst, options, capture_stderr, logs_dir)
    if not ok:
        print(f"Repair failed: {src}")
        if broken_playlist:
            broken_playlist.parent.mkdir(parents=True, exist_ok=True)
            with broken_playlist.open("a", encoding="utf-8") as handle:
                handle.write(str(src) + "\n")
            print(f"Appended failed file to {broken_playlist}")
        return 1
    print(f"Repaired: {dst}")
    return 0


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    options = build_options(args)
    broken_playlist = Path(args.broken_playlist) if args.broken_playlist else None

    if getattr(args, "single_file", None):
        return repair_single(
            Path(args.single_file),
            output_dir,
            options,
            args.capture_stderr,
            broken_playlist,
        )

    playlist_path = (
        Path(args.playlist)
        if args.playlist
        else Path("/Volumes/dotad/MUSIC/broken_files_unrepaired.m3u")
    )
    if broken_playlist is None:
        broken_playlist = playlist_path
    return repair_playlist(
        playlist_path,
        output_dir,
        options,
        args.capture_stderr,
        args.overwrite_playlist,
        broken_playlist,
    )


if __name__ == "__main__":
    raise SystemExit(main())
