"""Tools for analysing quarantine directories."""

from __future__ import annotations

import csv
import hashlib
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


def _which(cmd: str) -> Optional[str]:
    from shutil import which

    return which(cmd)


def ffprobe_info(path: Path, timeout: int = 3) -> dict:
    """Return duration/sample-rate metadata for *path* using ``ffprobe``."""

    ffprobe = _which("ffprobe")
    if ffprobe is None:
        raise FileNotFoundError("ffprobe not found in PATH")

    cmd = [
        ffprobe,
        "-nostdin",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=channels,sample_rate,nb_read_frames",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"duration": None, "sample_rate": None, "channels": None, "nb_read_frames": None}

    tokens = proc.stdout.strip().splitlines()
    info = {"duration": None, "sample_rate": None, "channels": None, "nb_read_frames": None}
    if not tokens:
        return info

    def _maybe_float(token: str) -> Optional[float]:
        try:
            return float(token)
        except ValueError:
            return None

    for token in tokens:
        value = _maybe_float(token)
        if value is None:
            continue
        if info["duration"] is None:
            info["duration"] = value
            continue
        if value > 10_000 and info["sample_rate"] is None:
            info["sample_rate"] = int(value)
            continue
        if value in {1.0, 2.0, 4.0, 6.0, 8.0} and info["channels"] is None:
            info["channels"] = int(value)
            continue
        if value >= 1 and info["nb_read_frames"] is None:
            info["nb_read_frames"] = int(value)

    return info


def compute_pcm_sha1(path: Path, timeout: int = 10) -> Optional[str]:
    """Decode *path* to PCM and return a SHA1 digest of the audio frames."""

    ffmpeg = _which("ffmpeg")
    if ffmpeg is None:
        return None

    cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-f", "wav", "-"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None

    assert proc.stdout is not None
    digest = hashlib.sha1()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None

    if proc.returncode != 0:
        return None

    while True:
        chunk = proc.stdout.read(65_536)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def windowed_fpcalc_count(
    path: Path,
    window: int = 30,
    *,
    step: Optional[int] = None,
    timeout_per_window: int = 5,
) -> int:
    """Return the number of distinct Chromaprint fingerprints for sliding windows."""

    ffmpeg = _which("ffmpeg")
    fpcalc = _which("fpcalc")
    if ffmpeg is None or fpcalc is None:
        return 0

    try:
        info = ffprobe_info(path)
    except Exception:
        return 0
    duration = info.get("duration") or 0
    if duration <= 0 or duration > 600:
        return 0

    fingerprints = set()
    offset = 0.0
    max_windows = 3
    step = step or (window - 10 if window > 10 else window)
    windows = 0

    while offset < duration and windows < max_windows:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cmd = [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-ss",
                str(offset),
                "-t",
                str(window),
                "-i",
                str(path),
                "-f",
                "wav",
                str(tmp_path),
            ]
            try:
                subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_per_window,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                break

            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                try:
                    proc = subprocess.run(
                        [fpcalc, str(tmp_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        timeout=3,
                        check=False,
                    )
                except subprocess.TimeoutExpired:
                    break
                for line in proc.stdout.splitlines():
                    if line.startswith("FINGERPRINT="):
                        fingerprints.add(line.split("=", 1)[1].strip())
                        break
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        offset += step
        windows += 1

    return len(fingerprints)


def detect_length_mismatch(path: Path) -> Tuple[Optional[float], Optional[float]]:
    """Return ``(reported, decoded)`` durations for *path*."""

    info = ffprobe_info(path)
    reported = info.get("duration")
    decoded = None
    sr = info.get("sample_rate")
    frames = info.get("nb_read_frames")
    if frames and sr:
        try:
            decoded = frames / float(sr)
        except Exception:
            decoded = None
    return reported, decoded


def analyse_track(path: Path) -> dict:
    info = ffprobe_info(path)
    reported = info.get("duration")
    sample_rate = info.get("sample_rate")
    channels = info.get("channels")
    frames = info.get("nb_read_frames")
    decoded = None
    if frames and sample_rate:
        decoded = frames / float(sample_rate)
    pcm = compute_pcm_sha1(path)
    fpcount = windowed_fpcalc_count(path)
    stitched = fpcount > 1
    truncated = False
    if decoded and reported and decoded > reported * 1.02:
        truncated = True
    return {
        "path": str(path),
        "size": path.stat().st_size if path.exists() else 0,
        "reported_duration": reported,
        "decoded_duration": decoded,
        "sample_rate": sample_rate,
        "channels": channels,
        "pcm_sha1": pcm,
        "window_fingerprint_count": fpcount,
        "stitched_flag": stitched,
        "truncated_flag": truncated,
    }


def analyse_quarantine(
    directory: Path,
    *,
    limit: Optional[int] = None,
    workers: int = 4,
) -> List[dict]:
    """Return rich metadata for FLAC files inside *directory*."""

    files = sorted(directory.rglob("*.flac"))
    if limit is not None and limit > 0:
        files = files[:limit]

    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(analyse_track, path): path for path in files}
        for future in as_completed(future_map):
            results.append(future.result())
    return results


def write_analysis_csv(rows: Sequence[dict], output: Path) -> None:
    """Write ``rows`` to *output* using the analysis CSV schema."""

    fieldnames = [
        "path",
        "size",
        "reported_duration",
        "decoded_duration",
        "sample_rate",
        "channels",
        "pcm_sha1",
        "window_fingerprint_count",
        "stitched_flag",
        "truncated_flag",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def simple_scan(directory: Path, *, limit: Optional[int] = None) -> List[dict]:
    """Return ``[{"path", "size", "duration"}, …]`` for quarantine files."""

    ffprobe = _which("ffprobe")
    if ffprobe is None:
        raise FileNotFoundError("ffprobe not found in PATH")

    files = sorted(directory.rglob("*.flac"))
    if limit is not None and limit > 0:
        files = files[:limit]

    rows: List[dict] = []
    for path in files:
        size = path.stat().st_size
        cmd = [
            ffprobe,
            "-nostdin",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
                check=False,
            )
            duration = float(proc.stdout.strip()) if proc.stdout.strip() else None
        except (ValueError, subprocess.TimeoutExpired):
            duration = None
        rows.append({"path": str(path), "size": size, "duration": duration})
    return rows


def detect_playback_issues(
    directory: Path,
    *,
    limit: Optional[int] = None,
) -> List[dict]:
    """Return rows describing playback duration mismatches."""

    files = sorted(directory.rglob("*.flac"))
    if limit is not None and limit > 0:
        files = files[:limit]

    rows: List[dict] = []
    for path in files:
        reported, decoded = detect_length_mismatch(path)
        ratio: Optional[float]
        try:
            if reported and decoded:
                ratio = decoded / reported
            else:
                ratio = None
        except Exception:
            ratio = None
        rows.append(
            {
                "path": str(path),
                "reported": reported,
                "decoded": decoded,
                "ratio": ratio,
            }
        )
    return rows


def write_rows_csv(fieldnames: Sequence[str], rows: Iterable[dict], output: Path) -> None:
    """Write arbitrary ``rows`` with the supplied ``fieldnames`` to *output*."""

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


__all__ = [
    "analyse_quarantine",
    "analyse_track",
    "compute_pcm_sha1",
    "detect_length_mismatch",
    "detect_playback_issues",
    "ffprobe_info",
    "simple_scan",
    "windowed_fpcalc_count",
    "write_analysis_csv",
    "write_rows_csv",
]
