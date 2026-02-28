"""
Stage 2: fast audio probes via ffprobe and ffmpeg.
Never modifies source files.
"""
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("tagslut.scan.validate")

EDGE_PROBE_SECONDS = 10.0


def probe_duration_ffprobe(path: Path) -> Optional[float]:
    """
    Measure actual audio duration via ffprobe.
    Returns None if ffprobe is unavailable or fails.
    """
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def decode_probe_edges(path: Path, duration: Optional[float] = None) -> List[str]:
    """
    Run ffmpeg error-only decode probe on first and last EDGE_PROBE_SECONDS.
    Returns list of error lines (empty = no errors detected).
    Returns [] without running if ffmpeg is not installed.
    """
    if shutil.which("ffmpeg") is None:
        return []

    errors: List[str] = []

    # Probe start
    cmd_start = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        "0",
        "-t",
        str(EDGE_PROBE_SECONDS),
        "-i",
        str(path),
        "-f",
        "null",
        "-",
    ]
    r = subprocess.run(cmd_start, capture_output=True, text=True)
    if r.stderr.strip():
        errors.extend(r.stderr.strip().splitlines())

    # Probe end (if we know duration)
    if duration and duration > EDGE_PROBE_SECONDS * 2:
        start_offset = duration - EDGE_PROBE_SECONDS
        cmd_end = [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            str(start_offset),
            "-t",
            str(EDGE_PROBE_SECONDS),
            "-i",
            str(path),
            "-f",
            "null",
            "-",
        ]
        r2 = subprocess.run(cmd_end, capture_output=True, text=True)
        if r2.stderr.strip():
            errors.extend(r2.stderr.strip().splitlines())

    return errors
