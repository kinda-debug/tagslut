#!/usr/bin/env python3

from __future__ import annotations

import argparse
import binascii
import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
# For base64 fingerprint decoding
import base64
import struct
import time

# Freeze detector state
last_progress_timestamp = time.time()
last_progress_file = None
freeze_detector_stop = threading.Event()
# Global progress counter for file scanning
scan_progress_lock = threading.Lock()
scan_processed_count = 0
scan_total_files = 0
scan_skipped_count = 0

# Protect updates to the global heartbeat state shared across worker threads
progress_update_lock = threading.Lock()

# Progress color cycling for gay flag colors
progress_color_index = 0
timestamp_color_index = 0
progress_word_offset = 0
last_timestamp_color = "\033[31m"  # Initial red
gay_flag_colors = [
    "\033[31m",  # Red
    "\033[33m",  # Yellow (for orange)
    "\033[33m",  # Yellow
    "\033[32m",  # Green
    "\033[34m",  # Blue
    "\033[35m"   # Purple
]

# Shared diagnostics manager configured at runtime
DIAGNOSTICS: Optional[DiagnosticsManager] = None

# Default timeouts (seconds); overridable via CLI
CMD_TIMEOUT: int = 45         # fpcalc, flac -t, ffprobe, metaflac
DECODE_TIMEOUT: int = 30     # ffmpeg streaming/decoding (PCM hash, segments) - reduced default to avoid long stalls


###############################################################################
# Utility helpers
###############################################################################


def colorize_path(path_str: str) -> str:
    """Colorize a path string with cyan for directories and white for filename."""
    try:
        p = Path(path_str)
        parts = p.parts
        if len(parts) <= 1:
            return f"\033[37m{path_str}\033[0m"  # white for file only
        dir_part = '/'.join(parts[:-1]) + '/'
        file_part = parts[-1]
        return f"\033[36m{dir_part}\033[0m\033[37m{file_part}\033[0m"  # cyan for dir, white for file
    except:
        return path_str


def heartbeat(path: Optional[Path] = None) -> None:
    """Record forward progress for the watchdog and freeze detector.

    Parameters
    ----------
    path:
        Optional filesystem path currently being processed. When provided the
        path is captured so the freeze detector can surface the last active
        file if progress stalls.
    """

    global last_progress_timestamp, last_progress_file
    with progress_update_lock:
        last_progress_timestamp = time.time()
        if path is not None:
            last_progress_file = str(path)


def log(message: str) -> None:
    """Print a human friendly timestamped log message."""

    timestamp = _dt.datetime.now().strftime("%H:%M:%S")
    
    # Colorize paths in the message
    if ": " in message:
        prefix, rest = message.split(": ", 1)
        if "/" in rest or "\\" in rest:  # detect path
            rest = colorize_path(rest.strip())
            message = f"{prefix}: {rest}"
    
    global timestamp_color_index
    timestamp_color = gay_flag_colors[timestamp_color_index % 6]
    timestamp_color_index += 1
    global last_timestamp_color
    last_timestamp_color = timestamp_color
    
    message_color = ""
    if "Progress" in message:
        # Color only the number in rainbow
        global progress_word_offset
        parts = message.split()
        if len(parts) >= 2:
            number = parts[1]
            color = gay_flag_colors[progress_word_offset % 6]
            progress_word_offset += 1
            parts[1] = f"{color}{number}\033[0m"
            message = " ".join(parts)
    elif "cached metadata" in message:
        message_color = "\033[35m"  # magenta for cached skips
    elif "Added broken file to playlist" in message:
        message_color = "\033[35m"  # magenta for added to playlist
    elif "WARNING" in message or "Error" in message or "freeze" in message.lower():
        message_color = "\033[33m"  # yellow for warnings/errors
    elif "Skipping" in message or "broken" in message or "quarantine" in message.lower():
        message_color = "\033[31m"  # red for skips/broken
    elif "Processed" in message or "completed" in message or "Killed" in message:
        if ": " in message:
            prefix, rest = message.split(": ", 1)
            # Color prefix green, rest lighter grey (white)
            print(f"{timestamp_color}[{timestamp}]\033[0m \033[32m{prefix}:\033[0m \033[37m{rest}\033[0m")
            return
        else:
            message_color = "\033[32m"  # green for success
    
    print(f"{timestamp_color}[{timestamp}]\033[0m {message_color}{message}\033[0m")

def log_progress(path: Path) -> None:
    """Print a progress log line for file scanning, including skipped and broken files."""
    global scan_processed_count, scan_total_files, scan_skipped_count
    with scan_progress_lock:
        scan_processed_count += 1
        processed = scan_processed_count
        total = scan_total_files
        skipped = scan_skipped_count
    # Calculate percent with 1 decimal
    percent = (processed / total * 100.0) if total else 0.0
    timestamp = _dt.datetime.now().strftime("%H:%M:%S")
    # Print progress and skipped/broken info
    if skipped > 0:
        print(f"[{timestamp}] Progress: {processed}/{total} ({percent:.1f}%) — {path.name} | Skipped: {skipped} files")
    else:
        print(f"[{timestamp}] Progress: {processed}/{total} ({percent:.1f}%) — {path.name}")
    heartbeat(path)


# Helper to log skipped files (broken or otherwise)
def log_skip(path: Path) -> None:
    """Print a progress log line for a skipped file, incrementing skipped count and showing processed/total."""
    global scan_skipped_count, scan_processed_count, scan_total_files
    with scan_progress_lock:
        scan_skipped_count += 1
        skipped = scan_skipped_count
        processed = scan_processed_count
        total = scan_total_files
    timestamp = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] Skipped: {skipped} files so far — {path.name} | Progress: {processed}/{total}")
    heartbeat(path)


def is_tool_available(tool: str) -> bool:
    """Return ``True`` when *tool* is present on ``PATH`` and executable."""

    return shutil.which(tool) is not None


def sha1_hex(data: bytes) -> str:
    """Return the hexadecimal SHA1 digest of *data*."""

    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def human_size(num_bytes: int) -> str:
    """Format *num_bytes* as a human readable string."""

    step = 1024.0
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num_bytes)
    for unit in units:
        if value < step:
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PiB"


def ensure_directory(path: Path) -> None:
    """Create *path* and all missing parents."""

    path.mkdir(parents=True, exist_ok=True)


###############################################################################
# Database management
###############################################################################


DB_SCHEMA_VERSION = 1


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the database schema when missing and manage migrations."""

    conn.execute("PRAGMA foreign_keys=ON")
    user_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if user_version == 0:
        _create_schema(conn)
        conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
        conn.commit()
        return
    if user_version != DB_SCHEMA_VERSION:
        raise RuntimeError(
            f"Unsupported database version {user_version}; expected {DB_SCHEMA_VERSION}."
        )


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create all database tables and indexes."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            inode INTEGER,
            size_bytes INTEGER,
            mtime REAL,
            codec TEXT,
            lossless INTEGER,
            duration REAL,
            bitrate_kbps REAL,
            stream_md5 TEXT,
            pcm_sha1 TEXT,
            fingerprint TEXT,
            fingerprint_hash TEXT,
            fuzzy_key TEXT,
            fuzzy_duration REAL,
            healthy INTEGER,
            health_note TEXT,
            exact_key_type TEXT,
            seg_h1 TEXT,
            seg_h2 TEXT,
            seg_h3 TEXT,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS file_signals (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            signal_type TEXT NOT NULL,
            signal_value TEXT,
            signal_aux TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS fp_bands (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            band_index INTEGER,
            hash TEXT
        );

        CREATE TABLE IF NOT EXISTS seg_slices (
            id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            slice_type TEXT NOT NULL,
            slice_index INTEGER,
            hash TEXT,
            start REAL,
            duration REAL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY,
            started_at TEXT,
            finished_at TEXT,
            root TEXT,
            options_json TEXT,
            dry_run INTEGER
        );

        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            group_key TEXT,
            method TEXT,
            keeper_file_id INTEGER REFERENCES files(id)
        );

        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY,
            group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
            file_id INTEGER NOT NULL REFERENCES files(id),
            role TEXT,
            action TEXT,
            dest_path TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
        CREATE INDEX IF NOT EXISTS idx_files_inode ON files(inode);
        CREATE INDEX IF NOT EXISTS idx_files_stream_md5 ON files(stream_md5);
        CREATE INDEX IF NOT EXISTS idx_files_pcm_sha1 ON files(pcm_sha1);
        CREATE INDEX IF NOT EXISTS idx_files_fp_hash ON files(fingerprint_hash);
        CREATE INDEX IF NOT EXISTS idx_files_fuzzy_key ON files(fuzzy_key);
        CREATE INDEX IF NOT EXISTS idx_files_seg_h1 ON files(seg_h1);
        CREATE INDEX IF NOT EXISTS idx_files_seg_h2 ON files(seg_h2);
        CREATE INDEX IF NOT EXISTS idx_files_seg_h3 ON files(seg_h3);
        CREATE INDEX IF NOT EXISTS idx_group_key ON groups(group_key);
        CREATE INDEX IF NOT EXISTS idx_group_members_file ON group_members(file_id);
        """
    )


###############################################################################
# Data containers
###############################################################################


@dataclass
class SegmentHashes:
    """Container for PCM segment hashes."""

    head: Optional[str] = None
    middle: Optional[str] = None
    tail: Optional[str] = None
    slide_hashes: List[str] = field(default_factory=list)
    trimmed_head: Optional[str] = None


@dataclass
class FileInfo:
    """Represents metadata and signal information for a single file."""

    id: int
    path: Path
    inode: int
    size_bytes: int
    mtime: float
    codec: Optional[str] = None
    lossless: bool = True
    duration: Optional[float] = None
    bitrate_kbps: Optional[float] = None
    stream_md5: Optional[str] = None
    pcm_sha1: Optional[str] = None
    fingerprint: Optional[List[int]] = None
    fingerprint_hash: Optional[str] = None
    fuzzy_key: Optional[str] = None
    fuzzy_duration: Optional[float] = None
    healthy: Optional[bool] = None
    health_note: Optional[str] = None
    exact_key_type: Optional[str] = None
    segments: SegmentHashes = field(default_factory=SegmentHashes)


@dataclass
class GroupResult:
    """Result for a deduplication group."""

    key: str
    method: str
    keeper: FileInfo
    losers: List[FileInfo]


@dataclass
class DiagnosticsManager:
    """Persist diagnostic dumps such as ``fpcalc`` stdout and watchdog notes."""

    root: Path
    dump_fpcalc: bool = True
    dump_decode: bool = True
    dump_watchdog: bool = True
    max_dump_bytes: int = 100 * 1024 * 1024

    def __post_init__(self) -> None:
        self.root = self._prepare_root(self.root)

    def _prepare_root(self, root: Path) -> Path:
        """Ensure *root* is writable; fall back to a runtime directory when necessary."""

        candidate = root.expanduser()
        try:
            ensure_directory(candidate)
            probe = candidate / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            fallback_base = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
            fallback = fallback_base / "dedupe_diagnostics"
            ensure_directory(fallback)
            log(
                "Diagnostic root %s unavailable; using %s instead" % (candidate.as_posix(), fallback.as_posix())
            )
            return fallback

    def _kind_dir(self, kind: str) -> Path:
        path = self.root / kind
        ensure_directory(path)
        return path

    def _safe_component(self, source: Path) -> str:
        base = source.name or "root"
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:48] or "entry"
        digest = hashlib.sha1(source.as_posix().encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        return f"{safe}_{digest}"

    def _write_json(
        self,
        kind: str,
        source: Path,
        payload_key: str,
        payload_value: Optional[str],
        **metadata: object,
    ) -> Path:
        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        record = {
            "timestamp": timestamp,
            "source": source.as_posix(),
            **metadata,
        }
        truncated = False
        text_value = payload_value or ""
        if text_value:
            encoded = text_value.encode("utf-8", "replace")
            if len(encoded) > self.max_dump_bytes:
                encoded = encoded[: self.max_dump_bytes]
                text_value = encoded.decode("utf-8", "ignore")
                truncated = True
        record[payload_key] = text_value
        if truncated:
            record[f"{payload_key}_truncated"] = True
        directory = self._kind_dir(kind)
        filename = f"{timestamp}_{self._safe_component(source)}.json"
        dump_path = directory / filename
        dump_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return dump_path

    def record_fpcalc(
        self,
        source: Path,
        stdout: str,
        command: Sequence[str],
        success: bool,
        error: Optional[str] = None,
    ) -> Optional[Path]:
        """Persist stdout/stderr from ``fpcalc`` for the given *source* path."""

        if not self.dump_fpcalc:
            return None
        metadata = {
            "command": list(command),
            "success": success,
        }
        if error:
            metadata["error"] = error
        return self._write_json("fpcalc", source, "stdout", stdout, **metadata)

    def record_decode(
        self,
        source: Path,
        stderr: str,
        command: Sequence[str],
        stage: str,
        success: bool,
        note: Optional[str] = None,
    ) -> Optional[Path]:
        """Persist diagnostic information for decoding/ffmpeg operations."""

        if not self.dump_decode:
            return None
        metadata = {
            "command": list(command),
            "stage": stage,
            "success": success,
        }
        if note:
            metadata["note"] = note
        return self._write_json("decode", source, "stderr", stderr, **metadata)

    def record_watchdog(self, message: str, context: Optional[str] = None) -> Optional[Path]:
        """Persist watchdog/freeze diagnostic entries."""

        if not self.dump_watchdog:
            return None
        metadata = {"context": context} if context else {}
        return self._write_json("watchdog", Path("/watchdog"), "message", message, **metadata)

    def latest(self, kind: str) -> Optional[Path]:
        """Return the newest diagnostic dump path for *kind* if available."""

        directory = self.root / kind
        if not directory.exists():
            return None
        candidates = []
        for candidate in directory.glob("*.json"):
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, candidate))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1] if candidates else None

###############################################################################
# External command helpers
###############################################################################


class CommandError(RuntimeError):
    """Raised when an external command fails."""


def run_command(command: Sequence[str], timeout: Optional[int] = None) -> str:
    """Execute *command* and return stdout; raises CommandError on failure/timeout."""
    effective_timeout = timeout if timeout is not None else CMD_TIMEOUT
    try:
        # Launch in process group for reliable killing
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError as exc:
        raise CommandError(str(exc)) from exc

    try:
        stdout, stderr = process.communicate(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        # Kill the process group
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        # Wait a bit for graceful shutdown
        import time
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
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        raise CommandError(f"Timeout executing {' '.join(command)}")

    if process.returncode != 0:
        cmd_str = ' '.join(command)
        raise CommandError(f"Command {cmd_str} failed: {stderr.strip()}")
    return stdout


###############################################################################
# Media probing and hashing
###############################################################################


def probe_ffprobe(path: Path) -> Dict[str, Optional[float]]:
    """Use ``ffprobe`` to gather codec, duration and bitrate information."""

    if not is_tool_available("ffprobe"):
        return {}

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:format_tags=MD5",
        "-show_entries",
        "stream=index,codec_name,codec_type,bit_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        heartbeat(path)
        output = run_command(cmd, timeout=CMD_TIMEOUT)
    except CommandError:
        return {}

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return {}

    result: Dict[str, Optional[float]] = {}

    fmt = data.get("format", {})
    duration = fmt.get("duration")
    if duration is not None:
        try:
            result["duration"] = float(duration)
        except (TypeError, ValueError):
            pass

    md5 = None
    tags = fmt.get("tags") if isinstance(fmt.get("tags"), dict) else {}
    if tags:
        md5 = tags.get("MD5")
    if md5:
        result["stream_md5"] = md5.strip().lower()

    streams = data.get("streams") or []
    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue
        result["codec"] = stream.get("codec_name")
        bit_rate = stream.get("bit_rate")
        if bit_rate:
            try:
                result["bitrate_kbps"] = float(bit_rate) / 1000.0
            except (TypeError, ValueError):
                pass
        break

    return result


def compute_metaflac_md5(path: Path) -> Optional[str]:
    """Return the FLAC stream MD5 via ``metaflac`` when available."""

    if not is_tool_available("metaflac"):
        return None
    try:
        heartbeat(path)
        output = run_command(["metaflac", "--show-md5sum", str(path)], timeout=CMD_TIMEOUT)
    except CommandError:
        return None
    value = output.strip().lower()
    if value and value != "0" * 32:
        return value
    return None


def compute_pcm_sha1(path: Path) -> Optional[str]:
    """Compute a SHA1 hash of the PCM stream via ``ffmpeg``."""

    if not is_tool_available("ffmpeg"):
        return None

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-",
    ]
    try:
        heartbeat(path)
        # Launch ffmpeg in its own process group so we can reliably kill only
        # the processes we spawned (avoid global pkill). POSIX only (macOS/Linux).
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    import time
    deadline = time.time() + DECODE_TIMEOUT
    digest = hashlib.sha1(usedforsecurity=False)
    assert process.stdout is not None
    stderr_chunks: List[bytes] = []
    while True:
        if time.time() > deadline:
            # Try to gracefully terminate the whole process group, then force-kill
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            process.wait()
            if process.stderr is not None:
                try:
                    stderr_chunks.append(process.stderr.read() or b"")
                    process.stderr.close()
                except Exception:
                    pass
            if DIAGNOSTICS is not None:
                DIAGNOSTICS.record_decode(
                    path,
                    b"".join(stderr_chunks).decode("utf-8", "replace"),
                    cmd,
                    stage="pcm_sha1",
                    success=False,
                    note="timeout",
                )
            return None
        chunk = process.stdout.read(65536)
        if not chunk:
            break
        digest.update(chunk)
        heartbeat(path)

    process.stdout.close()
    process.wait()
    stderr_text = ""
    if process.stderr is not None:
        try:
            stderr_chunks.append(process.stderr.read() or b"")
            process.stderr.close()
        except Exception:
            pass
    if stderr_chunks:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", "replace")
    success = process.returncode == 0
    if DIAGNOSTICS is not None:
        DIAGNOSTICS.record_decode(
            path,
            stderr_text,
            cmd,
            stage="pcm_sha1",
            success=success,
            note=None,
        )
    if not success:
        return None
    return digest.hexdigest()


def compute_segment_hash(
    path: Path, start: float, duration: float, sample_rate: int = 44100
) -> Optional[str]:
    """Hash a PCM excerpt using ``ffmpeg``.

    Parameters
    ----------
    path:
        Path to the audio file.
    start:
        Start time in seconds.
    duration:
        Excerpt length in seconds.
    sample_rate:
        Target PCM sample rate.
    """

    if not is_tool_available("ffmpeg"):
        return None

    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(path),
        "-t",
        f"{duration:.3f}",
        "-f",
        "s16le",
        "-ac",
        "2",
        "-ar",
        str(sample_rate),
        "-",
    ]
    try:
        heartbeat(path)
        # Launch ffmpeg in its own process group
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    import time
    deadline = time.time() + DECODE_TIMEOUT
    digest = hashlib.sha1(usedforsecurity=False)
    assert process.stdout is not None
    stderr_chunks: List[bytes] = []
    while True:
        if time.time() > deadline:
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
            if process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass
            process.wait()
            if process.stderr is not None:
                try:
                    stderr_chunks.append(process.stderr.read() or b"")
                    process.stderr.close()
                except Exception:
                    pass
            if DIAGNOSTICS is not None:
                DIAGNOSTICS.record_decode(
                    path,
                    b"".join(stderr_chunks).decode("utf-8", "replace"),
                    cmd,
                    stage="segment_hash",
                    success=False,
                    note="timeout",
                )
            return None
        chunk = process.stdout.read(65536)
        if not chunk:
            break
        digest.update(chunk)
        heartbeat(path)

    process.stdout.close()
    process.wait()
    stderr_text = ""
    if process.stderr is not None:
        try:
            stderr_chunks.append(process.stderr.read() or b"")
            process.stderr.close()
        except Exception:
            pass
    if stderr_chunks:
        stderr_text = b"".join(stderr_chunks).decode("utf-8", "replace")
    success = process.returncode == 0
    if DIAGNOSTICS is not None:
        DIAGNOSTICS.record_decode(
            path,
            stderr_text,
            cmd,
            stage="segment_hash",
            success=success,
        )
    if not success:
        return None
    return digest.hexdigest()


def compute_segment_hashes(
    path: Path,
    duration: Optional[float],
    seg_length: float,
    enable_sliding: bool,
    slide_step: float,
    max_slices: int,
    include_trimmed: bool,
) -> SegmentHashes:
    """Compute hashes for head/middle/tail and optional sliding excerpts."""

    hashes = SegmentHashes()
    if duration is None:
        return hashes

    duration = max(duration, 0.0)
    seg_length = min(seg_length, duration)
    if seg_length <= 0:
        return hashes

    heartbeat(path)
    hashes.head = compute_segment_hash(path, 0.0, seg_length)
    mid_start = max((duration - seg_length) / 2.0, 0.0)
    heartbeat(path)
    hashes.middle = compute_segment_hash(path, mid_start, seg_length)
    tail_start = max(duration - seg_length, 0.0)
    heartbeat(path)
    hashes.tail = compute_segment_hash(path, tail_start, seg_length)

    if include_trimmed:
        trim_start = min(1.0, max(duration - seg_length, 0.0))
        heartbeat(path)
        hashes.trimmed_head = compute_segment_hash(path, trim_start, seg_length)

    if enable_sliding and max_slices > 0 and slide_step > 0:
        for index in range(max_slices):
            start = slide_step * index
            if start + seg_length > duration:
                break
            heartbeat(path)
            segment_hash = compute_segment_hash(path, start, seg_length)
            if segment_hash:
                hashes.slide_hashes.append(segment_hash)

    return hashes


def _normalize_base64_payload(data: str) -> str:
    """Return a normalized base64 payload using the standard alphabet.

    The helper strips whitespace, converts URL-safe variants to the standard
    alphabet, and appends padding when required. Values whose length modulo 4
    equals 1 are impossible to decode and raise ``ValueError`` so callers can
    treat them as malformed without raising cryptic ``binascii`` errors.
    """

    cleaned = "".join(data.split())
    cleaned = cleaned.replace("-", "+").replace("_", "/")
    remainder = len(cleaned) % 4
    if remainder == 1:
        raise ValueError("Invalid base64 length")
    if remainder:
        cleaned += "=" * (4 - remainder)
    return cleaned


def _decode_base64_fingerprint(encoded: str) -> Optional[List[int]]:
    """Decode a base64-encoded Chromaprint fingerprint into integers."""

    try:
        normalized = _normalize_base64_payload(encoded)
    except ValueError:
        return None
    try:
        fingerprint_bytes = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(fingerprint_bytes) % 4 != 0 or not fingerprint_bytes:
        return None
    count = len(fingerprint_bytes) // 4
    try:
        return list(struct.unpack(f"<{count}i", fingerprint_bytes))
    except struct.error:
        return None


def _coerce_fingerprint_sequence(values: Iterable[object]) -> Optional[List[int]]:
    """Convert *values* to a list of integers if possible."""

    result: List[int] = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            return None
    return result or None


def parse_fpcalc_output(output: str) -> Tuple[Optional[List[int]], Optional[str]]:
    """Parse ``fpcalc`` output and return the fingerprint and its hash."""

    fingerprint: Optional[List[int]] = None
    if not output.strip():
        return (None, None)

    def _finalize(values: Optional[List[int]]) -> Tuple[Optional[List[int]], Optional[str]]:
        if not values:
            return (None, None)
        hash_hex = sha1_hex(",".join(str(v) for v in values).encode("utf-8"))
        return (values, hash_hex)

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        data = None
    else:
        if isinstance(data, dict):
            fp_value = data.get("fingerprint") or data.get("chromaprint")
            if isinstance(fp_value, list):
                fingerprint = _coerce_fingerprint_sequence(fp_value)
                if fingerprint:
                    return _finalize(fingerprint)
            elif isinstance(fp_value, str):
                fingerprint = _decode_base64_fingerprint(fp_value)
                if fingerprint:
                    return _finalize(fingerprint)
                fingerprint = _coerce_fingerprint_sequence(fp_value.split(","))
                if fingerprint:
                    return _finalize(fingerprint)
        elif isinstance(data, list):
            fingerprint = _coerce_fingerprint_sequence(data)
            if fingerprint:
                return _finalize(fingerprint)

    for line in output.splitlines():
        if not line.startswith("FINGERPRINT="):
            continue
        raw = line.split("=", 1)[1]
        fingerprint = _decode_base64_fingerprint(raw)
        if fingerprint:
            return _finalize(fingerprint)
        fingerprint = _coerce_fingerprint_sequence(part for part in raw.split(",") if part)
        if fingerprint:
            return _finalize(fingerprint)
        break

    return (None, None)


def compute_fingerprint(path: Path) -> Tuple[Optional[List[int]], Optional[str]]:
    """Compute the chromaprint fingerprint using ``fpcalc``."""

    if not is_tool_available("fpcalc"):
        return (None, None)
    commands = [["fpcalc", "-json", str(path)], ["fpcalc", str(path)]]
    for command in commands:
        try:
            heartbeat(path)
            output = run_command(command, timeout=CMD_TIMEOUT)
        except CommandError as exc:
            if DIAGNOSTICS is not None:
                DIAGNOSTICS.record_fpcalc(path, "", command, success=False, error=str(exc))
            continue
        if DIAGNOSTICS is not None:
            DIAGNOSTICS.record_fpcalc(path, output, command, success=True)
        fingerprint, digest = parse_fpcalc_output(output)
        if fingerprint is not None and digest is not None:
            return (fingerprint, digest)
    return (None, None)


def check_health(path: Path) -> Tuple[Optional[bool], Optional[str]]:
    """Check file health via ``flac -t`` or ``ffmpeg`` decoding."""


    if is_tool_available("flac"):
        try:
            heartbeat(path)
            run_command(["flac", "-s", "-t", str(path)], timeout=CMD_TIMEOUT)
            return (True, "flac -t")
        except CommandError as exc:
            return (False, f"flac -t failed: {exc}")

    if is_tool_available("ffmpeg"):
        cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"]
        try:
            heartbeat(path)
            run_command(cmd, timeout=CMD_TIMEOUT)
            return (True, "ffmpeg decode")
        except CommandError as exc:
            return (False, f"ffmpeg decode failed: {exc}")

    return (None, "health check unavailable")


###############################################################################
# Fingerprint similarity
###############################################################################


def fingerprint_similarity(
    fp_a: Sequence[int],
    fp_b: Sequence[int],
    max_shift: int,
    min_overlap: int,
) -> Tuple[float, int, int]:
    """Return the similarity ratio, shift and overlap between fingerprints."""

    if not fp_a or not fp_b:
        return (0.0, 0, 0)

    best_ratio = 0.0
    best_shift = 0
    best_overlap = 0

    for shift in range(-max_shift, max_shift + 1):
        matches = 0
        overlap = 0
        for index_a, value in enumerate(fp_a):
            index_b = index_a + shift
            if index_b < 0 or index_b >= len(fp_b):
                continue
            overlap += 1
            if value == fp_b[index_b]:
                matches += 1
        if overlap < min_overlap:
            continue
        ratio = matches / overlap if overlap else 0.0
        if ratio > best_ratio:
            best_ratio = ratio
            best_shift = shift
            best_overlap = overlap

    return (best_ratio, best_shift, best_overlap)


###############################################################################
# Fuzzy key generation
###############################################################################


def normalize_filename(name: str, aggressive: bool) -> str:
    """Return a lowercase normalized version of *name* suitable for fuzzy keys."""

    cleaned = name.lower()
    cleaned = cleaned.replace("_", " ")
    for token in ["feat.", "ft.", "featuring", "(live)"]:
        cleaned = cleaned.replace(token, " ")
    if aggressive:
        for token in ["remix", "edit", "mix", "version"]:
            cleaned = cleaned.replace(token, " ")
    allowed = []
    for char in cleaned:
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-"}:
            allowed.append(" ")
    normalized = " ".join(part for part in "".join(allowed).split() if part)
    return normalized


def build_fuzzy_key(path: Path, aggressive: bool) -> str:
    """Construct a fuzzy key using the file name and parent directory."""

    parts = [normalize_filename(path.stem, aggressive)]
    if path.parent != path:
        parts.append(normalize_filename(path.parent.name, aggressive))
    return " :: ".join(part for part in parts if part)


###############################################################################
###############################################################################
# File scanning and persistence
###############################################################################


def load_file_from_db(conn: sqlite3.Connection, path: Path) -> Optional[FileInfo]:

    """Return a :class:`FileInfo` loaded from the database."""

    cursor = conn.execute("SELECT * FROM files WHERE path=?", (str(path),))
    row = cursor.fetchone()
    if not row:
        return None
    columns = [desc[0] for desc in cursor.description]
    data = dict(zip(columns, row))

    segments = SegmentHashes(
        head=data.get("seg_h1"),
        middle=data.get("seg_h2"),
        tail=data.get("seg_h3"),
    )

    fingerprint_values: Optional[List[int]] = None
    if data.get("fingerprint"):
        try:
            fingerprint_values = json.loads(data["fingerprint"])
            if not isinstance(fingerprint_values, list):
                fingerprint_values = None
        except json.JSONDecodeError:
            fingerprint_values = None

    return FileInfo(
        id=data["id"],
        path=Path(data["path"]),
        inode=data.get("inode") or 0,
        size_bytes=data.get("size_bytes") or 0,
        mtime=data.get("mtime") or 0.0,
        codec=data.get("codec"),
        lossless=bool(data.get("lossless") or False),
        duration=data.get("duration"),
        bitrate_kbps=data.get("bitrate_kbps"),
        stream_md5=data.get("stream_md5"),
        pcm_sha1=data.get("pcm_sha1"),
        fingerprint=fingerprint_values,
        fingerprint_hash=data.get("fingerprint_hash"),
        fuzzy_key=data.get("fuzzy_key"),
        fuzzy_duration=data.get("fuzzy_duration"),
        healthy=None if data.get("healthy") is None else bool(data.get("healthy")),
        health_note=data.get("health_note"),
        exact_key_type=data.get("exact_key_type"),
        segments=segments,
    )


def load_all_files_from_db(conn: sqlite3.Connection) -> List[FileInfo]:
    """Return all :class:`FileInfo` entries from the database."""

    files = []
    cursor = conn.execute("SELECT * FROM files")
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        data = dict(zip(columns, row))

        segments = SegmentHashes(
            head=data.get("seg_h1"),
            middle=data.get("seg_h2"),
            tail=data.get("seg_h3"),
        )

        fingerprint_values: Optional[List[int]] = None
        if data.get("fingerprint"):
            try:
                fingerprint_values = json.loads(data["fingerprint"])
                if not isinstance(fingerprint_values, list):
                    fingerprint_values = None
            except json.JSONDecodeError:
                fingerprint_values = None

        file_info = FileInfo(
            id=data["id"],
            path=Path(data["path"]),
            inode=data.get("inode") or 0,
            size_bytes=data.get("size_bytes") or 0,
            mtime=data.get("mtime") or 0.0,
            codec=data.get("codec"),
            lossless=bool(data.get("lossless") or False),
            duration=data.get("duration"),
            bitrate_kbps=data.get("bitrate_kbps"),
            stream_md5=data.get("stream_md5"),
            pcm_sha1=data.get("pcm_sha1"),
            fingerprint=fingerprint_values,
            fingerprint_hash=data.get("fingerprint_hash"),
            fuzzy_key=data.get("fuzzy_key"),
            fuzzy_duration=data.get("fuzzy_duration"),
            healthy=None if data.get("healthy") is None else bool(data.get("healthy")),
            health_note=data.get("health_note"),
            exact_key_type=data.get("exact_key_type"),
            segments=segments,
        )
        files.append(file_info)

    return files


def upsert_file(conn: sqlite3.Connection, info: FileInfo) -> None:
    """Insert or update a :class:`FileInfo` in the database."""

    now = _dt.datetime.now(_dt.UTC).isoformat()
    fingerprint_json = json.dumps(info.fingerprint) if info.fingerprint else None
    payload = (
        info.path.as_posix(),
        info.inode,
        info.size_bytes,
        info.mtime,
        info.codec,
        int(info.lossless),
        info.duration,
        info.bitrate_kbps,
        info.stream_md5,
        info.pcm_sha1,
        fingerprint_json,
        info.fingerprint_hash,
        info.fuzzy_key,
        info.fuzzy_duration,
        None if info.healthy is None else int(info.healthy),
        info.health_note,
        info.exact_key_type,
        info.segments.head,
        info.segments.middle,
        info.segments.tail,
        now,
        now,
        info.id,
    )

    conn.execute(
        textwrap.dedent(
            """
            INSERT INTO files (
                path, inode, size_bytes, mtime, codec, lossless, duration,
                bitrate_kbps, stream_md5, pcm_sha1, fingerprint, fingerprint_hash,
                fuzzy_key, fuzzy_duration, healthy, health_note, exact_key_type,
                seg_h1, seg_h2, seg_h3, created_at, updated_at, id
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(id) DO UPDATE SET
                path=excluded.path,
                inode=excluded.inode,
                size_bytes=excluded.size_bytes,
                mtime=excluded.mtime,
                codec=excluded.codec,
                lossless=excluded.lossless,
                duration=excluded.duration,
                bitrate_kbps=excluded.bitrate_kbps,
                stream_md5=excluded.stream_md5,
                pcm_sha1=excluded.pcm_sha1,
                fingerprint=excluded.fingerprint,
                fingerprint_hash=excluded.fingerprint_hash,
                fuzzy_key=excluded.fuzzy_key,
                fuzzy_duration=excluded.fuzzy_duration,
                healthy=excluded.healthy,
                health_note=excluded.health_note,
                exact_key_type=excluded.exact_key_type,
                seg_h1=excluded.seg_h1,
                seg_h2=excluded.seg_h2,
                seg_h3=excluded.seg_h3,
                updated_at=excluded.updated_at
            """
        ),
        payload,
    )
    conn.commit()


def insert_segments(conn: sqlite3.Connection, file_id: int, segments: SegmentHashes) -> None:
    """Persist segment hashes into ``seg_slices``."""

    conn.execute("DELETE FROM seg_slices WHERE file_id=?", (file_id,))
    entries: List[Tuple[int, str, int, str, float, float]] = []
    if segments.head:
        entries.append((file_id, "HEAD", 0, segments.head, 0.0, 0.0))
    if segments.middle:
        entries.append((file_id, "MIDDLE", 0, segments.middle, 0.0, 0.0))
    if segments.tail:
        entries.append((file_id, "TAIL", 0, segments.tail, 0.0, 0.0))
    if segments.trimmed_head:
        entries.append((file_id, "TRIM_HEAD", 0, segments.trimmed_head, 0.0, 0.0))
    for index, value in enumerate(segments.slide_hashes):
        entries.append((file_id, "SLIDE", index, value, 0.0, 0.0))
    conn.executemany(
        """
        INSERT INTO seg_slices (file_id, slice_type, slice_index, hash, start, duration)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        entries,
    )
    conn.commit()


def load_slide_hashes(conn: sqlite3.Connection, file_id: int, segments: SegmentHashes) -> None:
    """Populate ``slide_hashes`` and ``trimmed_head`` from the database."""

    cursor = conn.execute(
        "SELECT slice_type, slice_index, hash FROM seg_slices WHERE file_id=?",
        (file_id,),
    )
    slides: List[str] = []
    trimmed: Optional[str] = None
    for slice_type, slice_index, hash_value in cursor.fetchall():
        if slice_type == "SLIDE":
            slides.append(hash_value)
        elif slice_type == "TRIM_HEAD":
            trimmed = hash_value
    segments.slide_hashes = slides
    segments.trimmed_head = trimmed


def store_file_signals(conn: sqlite3.Connection, info: FileInfo) -> None:
    """Persist hashes and fingerprints to ``file_signals`` and ``fp_bands``."""

    conn.execute("DELETE FROM file_signals WHERE file_id=?", (info.id,))
    conn.execute("DELETE FROM fp_bands WHERE file_id=?", (info.id,))
    now = _dt.datetime.now(_dt.UTC).isoformat()
    entries: List[Tuple[int, str, Optional[str], Optional[str], str]] = []
    if info.stream_md5:
        entries.append((info.id, "stream_md5", info.stream_md5, None, now))
    if info.pcm_sha1:
        entries.append((info.id, "pcm_sha1", info.pcm_sha1, None, now))
    if info.fingerprint:
        entries.append(
            (
                info.id,
                "chromaprint",
                json.dumps(info.fingerprint),
                info.fingerprint_hash,
                now,
            )
        )
        insert_fp_bands(conn, info.id, info.fingerprint)
    conn.executemany(
        """
        INSERT INTO file_signals (file_id, signal_type, signal_value, signal_aux, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        entries,
    )
    conn.commit()


def insert_fp_bands(conn: sqlite3.Connection, file_id: int, fingerprint: Sequence[int]) -> None:
    """Store coarse hashes of fingerprint bands for quick lookups."""

    window = 32
    band_entries: List[Tuple[int, int, str]] = []
    for index in range(0, len(fingerprint), window):
        chunk = fingerprint[index : index + window]
        if not chunk:
            continue
        chunk_bytes = ",".join(str(v) for v in chunk).encode("utf-8")
        band_hash = sha1_hex(chunk_bytes)
        band_entries.append((file_id, index // window, band_hash))
    conn.executemany(
        """
        INSERT INTO fp_bands (file_id, band_index, hash) VALUES (?, ?, ?)
        """,
        band_entries,
    )
    conn.commit()


###############################################################################
# Grouping and scoring
###############################################################################


def choose_winner(files: Sequence[FileInfo]) -> FileInfo:
    """Select the best candidate according to scoring rules."""

    def score(file: FileInfo) -> Tuple[int, int, float, float, float]:
        healthy = 1 if file.healthy else 0
        lossless = 1 if file.lossless else 0
        duration = file.duration or 0.0
        bitrate = file.bitrate_kbps or 0.0
        mtime = file.mtime
        return (healthy, lossless, duration, bitrate, mtime)

    return sorted(files, key=score, reverse=True)[0]


def build_groups(
    files: Sequence[FileInfo],
    fp_sim_ratio: float,
    fp_sim_shift: int,
    fp_sim_min_overlap: int,
    use_fingerprint: bool,
    use_segwin: bool,
    segwin_min_matches: int,
    use_slide: bool,
    fuzzy_duration_tol: float,
) -> List[GroupResult]:
    """Group files using the staged deduplication pipeline."""

    by_id = {file.id: file for file in files}
    remaining = set(by_id.keys())
    groups: List[GroupResult] = []
    segwin_min_matches = max(1, segwin_min_matches)

    def register_group(key: str, method: str, members: List[FileInfo]) -> None:
        keeper = choose_winner(members)
        losers = [file for file in members if file != keeper]
        if not losers:
            return
        for member in members:
            remaining.discard(member.id)
        groups.append(GroupResult(key=key, method=method, keeper=keeper, losers=losers))

    # Stage A: EXACT
    key_to_members: Dict[str, List[FileInfo]] = {}
    for file in files:
        if file.id not in remaining:
            continue
        if file.stream_md5:
            key_to_members.setdefault(f"MD5:{file.stream_md5}", []).append(file)
            file.exact_key_type = "stream_md5"
        elif file.pcm_sha1:
            key_to_members.setdefault(f"PCM:{file.pcm_sha1}", []).append(file)
            file.exact_key_type = "pcm_sha1"
    for key, members in key_to_members.items():
        if len(members) > 1:
            register_group(key, "EXACT", members)

    if use_fingerprint:
        # Stage B: FPRINT equality
        key_to_members = {}
        for file in files:
            if file.id not in remaining:
                continue
            if file.fingerprint_hash:
                key_to_members.setdefault(file.fingerprint_hash, []).append(file)
        for key, members in key_to_members.items():
            if len(members) > 1:
                register_group(f"FP:{key}", "FPRINT", members)

        # Stage C: FPRINT similarity
        fp_candidates = [file for file in files if file.id in remaining and file.fingerprint]
        used_pairs: Set[Tuple[int, int]] = set()
        for i, file_a in enumerate(fp_candidates):
            for file_b in fp_candidates[i + 1 :]:
                pair = tuple(sorted((file_a.id, file_b.id)))
                if pair in used_pairs:
                    continue
                ratio, shift, overlap = fingerprint_similarity(
                    file_a.fingerprint or [],
                    file_b.fingerprint or [],
                    fp_sim_shift,
                    fp_sim_min_overlap,
                )
                if ratio >= fp_sim_ratio and overlap >= fp_sim_min_overlap:
                    register_group(
                        key=f"FPS:{file_a.id}:{file_b.id}",
                        method=f"FPRINT_SIM(r={ratio:.2f},s={shift})",
                        members=[file_a, file_b],
                    )
                    used_pairs.add(pair)

    # Stage D: segment windows head/mid/tail
    if use_segwin:
        seg_candidates = [
            file
            for file in files
            if file.id in remaining
            and any([file.segments.head, file.segments.middle, file.segments.tail])
        ]
        parent: Dict[int, int] = {file.id: file.id for file in seg_candidates}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(a: int, b: int) -> None:
            root_a = find(a)
            root_b = find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for i, file_a in enumerate(seg_candidates):
            for file_b in seg_candidates[i + 1 :]:
                matches = 0
                if file_a.segments.head and file_a.segments.head == file_b.segments.head:
                    matches += 1
                if file_a.segments.middle and file_a.segments.middle == file_b.segments.middle:
                    matches += 1
                if file_a.segments.tail and file_a.segments.tail == file_b.segments.tail:
                    matches += 1
                if (
                    file_a.segments.trimmed_head
                    and file_b.segments.trimmed_head
                    and file_a.segments.trimmed_head == file_b.segments.trimmed_head
                ):
                    matches += 1
                if matches >= segwin_min_matches:
                    union(file_a.id, file_b.id)

        groups_by_root: Dict[int, List[FileInfo]] = {}
        for candidate in seg_candidates:
            root = find(candidate.id)
            groups_by_root.setdefault(root, []).append(candidate)
        for members in groups_by_root.values():
            if len(members) > 1 and all(member.id in remaining for member in members):
                key = "SEGWIN:" + ",".join(str(member.id) for member in sorted(members, key=lambda f: f.id))
                register_group(key, f"SEGWIN(m>={segwin_min_matches})", members)

    # Stage E: sliding windows (optional)
    if use_slide:
        slide_candidates = [
            file for file in files if file.id in remaining and file.segments.slide_hashes
        ]
        parent: Dict[int, int] = {file.id: file.id for file in slide_candidates}
        seen: Dict[str, int] = {}

        def find_slide(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union_slide(a: int, b: int) -> None:
            root_a = find_slide(a)
            root_b = find_slide(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for file in slide_candidates:
            for slide_hash in file.segments.slide_hashes:
                if slide_hash in seen:
                    union_slide(file.id, seen[slide_hash])
                else:
                    seen[slide_hash] = file.id

        slide_groups: Dict[int, List[FileInfo]] = {}
        for file in slide_candidates:
            root = find_slide(file.id)
            slide_groups.setdefault(root, []).append(file)
        for members in slide_groups.values():
            if len(members) > 1 and all(member.id in remaining for member in members):
                key = "SEGWIN_SLIDE:" + ",".join(
                    str(member.id) for member in sorted(members, key=lambda f: f.id)
                )
                register_group(key, "SEGWIN_SLIDE", members)

    # Stage F: fuzzy key
    fuzzy_map: Dict[str, List[FileInfo]] = {}
    for file in files:
        if file.id not in remaining:
            continue
        if not file.fuzzy_key or file.duration is None:
            continue
        fuzzy_map.setdefault(file.fuzzy_key, []).append(file)
    for key, members in fuzzy_map.items():
        bucket: List[FileInfo] = []
        for file in members:
            added = False
            for candidate in bucket:
                dur_a = file.duration or 0.0
                dur_b = candidate.duration or 0.0
                if abs(dur_a - dur_b) <= fuzzy_duration_tol:
                    register_group(
                        key=f"FUZZY:{key}", method="FUZZY", members=[file, candidate]
                    )
                    added = True
                    break
            if not added:
                bucket.append(file)

    return groups


###############################################################################
# CSV report generation
###############################################################################


CSV_HEADERS = [
    "group_key",
    "method",
    "keep",
    "path",
    "name",
    "ext",
    "codec",
    "lossless",
    "size_bytes",
    "size_human",
    "duration_sec",
    "bitrate_kbps",
    "healthy",
    "health_note",
    "exact_key_type",
    "action",
    "dest",
]


def group_to_rows(group: GroupResult, trash_dir: Path, commit: bool) -> List[List[str]]:
    """Convert a group into CSV rows."""

    rows: List[List[str]] = []
    for file in [group.keeper] + group.losers:
        name = file.path.name
        ext = file.path.suffix.lower().lstrip(".")
        action = "keep" if file == group.keeper else ("move" if commit else "plan")
        dest = ""
        if file != group.keeper:
            dest_path = plan_trash_destination(trash_dir, file.path)
            dest = dest_path.as_posix()
        row = [
            group.key,
            group.method,
            "yes" if file == group.keeper else "no",
            file.path.as_posix(),
            name,
            ext,
            file.codec or "",
            "yes" if file.lossless else "no",
            str(file.size_bytes),
            human_size(file.size_bytes),
            f"{file.duration:.3f}" if file.duration is not None else "",
            f"{file.bitrate_kbps:.1f}" if file.bitrate_kbps is not None else "",
            "yes" if file.healthy else ("no" if file.healthy is False else ""),
            file.health_note or "",
            file.exact_key_type or "",
            action,
            dest,
        ]
        rows.append(row)
    return rows


def write_csv(
    report_path: Path, groups: Sequence[GroupResult], trash_dir: Path, commit: bool
) -> None:
    """Write the deduplication plan to *report_path*."""

    ensure_directory(report_path.parent)
    with report_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        for group in groups:
            for row in group_to_rows(group, trash_dir, commit):
                writer.writerow(row)


###############################################################################
# File operations
###############################################################################


def plan_trash_destination(trash_dir: Path, file_path: Path) -> Path:
    """Return the destination inside the trash directory preserving structure."""

    try:
        rel = file_path.relative_to(file_path.anchor)
    except ValueError:
        rel = Path(file_path.name)
    return trash_dir.joinpath(rel)


def move_duplicates(groups: Sequence[GroupResult], trash_dir: Path) -> None:
    """Move loser files to the trash directory."""

    ensure_directory(trash_dir)
    for group in groups:
        for file in group.losers:
            dest = plan_trash_destination(trash_dir, file.path)
            ensure_directory(dest.parent)
            log(f"Moving {file.path} -> {dest}")
            shutil.move(file.path.as_posix(), dest.as_posix())


###############################################################################
# Run orchestration
###############################################################################


class GracefulShutdown:
    """Signal handler that allows the script to stop gracefully."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._sigint_count = 0

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._handler)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _handler(self, signum, frame) -> None:  # pragma: no cover
        self._sigint_count += 1
        if self._sigint_count == 1:
            log("Received Ctrl-C — finishing current tasks then stopping… (press Ctrl-C again to abort now)")
            self._stop_event.set()
        else:
            log("Second Ctrl-C — aborting immediately.")
            os._exit(130)


def scan_files(
    root: Path,
    workers: int = 1,
    skip_broken: bool = False,
    auto_quarantine: bool = False,
    **kwargs,
) -> List[FileInfo]:
    """Walk the filesystem and update cached :class:`FileInfo` entries."""

    # Reset shared heartbeat/freeze state for this scan
    freeze_detector_stop.clear()
    heartbeat()

    # Helper to append to broken playlist, avoiding duplicates
    broken_playlist_set = set()
    broken_playlist_path = kwargs.get("broken_playlist_path")
    if broken_playlist_path and os.path.exists(broken_playlist_path):
        with open(broken_playlist_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    broken_playlist_set.add(line)

    def append_broken_playlist(path: Path):
        if not broken_playlist_path:
            return
        abs_path = str(path.resolve())
        if abs_path in broken_playlist_set:
            return
        try:
            Path(broken_playlist_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        with open(broken_playlist_path, "a") as f:
            f.write(abs_path + "\n")
        broken_playlist_set.add(abs_path)

    # Use provided watchdog timeout when available; fallback to a generous default
    WATCHDOG_TIMEOUT = int(kwargs.get("watchdog_timeout", 300) or 300)
    def watchdog():
        import time
        while not freeze_detector_stop.is_set():
            time.sleep(5)
            if time.time() - last_progress_timestamp > WATCHDOG_TIMEOUT:
                # Prefer logging and requesting a graceful stop over hard-killing the process.
                print(f"[WATCHDOG] No progress for {WATCHDOG_TIMEOUT} seconds. Requesting shutdown.", flush=True)
                if DIAGNOSTICS is not None:
                    DIAGNOSTICS.record_watchdog(
                        f"No progress for {WATCHDOG_TIMEOUT} seconds",
                        context=last_progress_file,
                    )
                # Signal the freeze detector and request shutdown if available
                try:
                    freeze_detector_stop.set()
                except Exception:
                    pass
                # If a shutdown object was passed in kwargs, try to set its stop event
                try:
                    sd = kwargs.get("shutdown")
                    if sd and hasattr(sd, "_stop_event"):
                        sd._stop_event.set()
                except Exception:
                    pass
                # After requesting shutdown, exit the watchdog thread
                freeze_detector_stop.set()
                return

    threading.Thread(target=watchdog, daemon=True).start()
    """Walk the filesystem and update cached :class:`FileInfo` entries."""

    global last_progress_timestamp, last_progress_file

    # Freeze detector watcher logic
    def freeze_detector_watcher(quarantine_dir=None):
        import time
        while not freeze_detector_stop.is_set():
            time.sleep(5)
            now = time.time()
            # print(f"\033[33m[FREEZE WATCH]\033[0m now={now:.1f}, last={last_progress_timestamp:.1f}, "
            #       f"diff={now - last_progress_timestamp:.1f}, file={last_progress_file}", flush=True)
            if now - last_progress_timestamp > 30 and last_progress_file:
                print(f"[FREEZE DETECTOR] Triggered: no progress for 30s on "
                      f"{last_progress_file}", flush=True)
                log(f"WARNING: No progress for 30s. Last file: {last_progress_file}")
                if DIAGNOSTICS is not None:
                    DIAGNOSTICS.record_watchdog(
                        "Freeze detector triggered",
                        context=last_progress_file,
                    )
                # Kill any stalled ffmpeg processes
                try:
                    subprocess.run(["pkill", "-9", "ffmpeg"],
                                   check=False, timeout=5)
                    log("Killed stalled ffmpeg processes")
                except Exception as e:
                    log(f"Failed to kill ffmpeg: {e}")
                if quarantine_dir and os.path.exists(last_progress_file):
                    try:
                        os.makedirs(quarantine_dir, exist_ok=True)
                        dest = os.path.join(quarantine_dir, os.path.basename(last_progress_file))
                        shutil.move(last_progress_file, dest)
                        log(f"Moved frozen file to quarantine: {dest}")
                    except Exception as e:
                        log(f"Failed to quarantine file: {e}")
                freeze_detector_stop.set()

    # Start freeze detector watcher after docstring
    quarantine_dir = None
    if auto_quarantine:
        quarantine_dir = os.path.join(str(root), '_BROKEN')
    watcher = threading.Thread(target=freeze_detector_watcher, args=(quarantine_dir,), daemon=True)
    watcher.start()

    files: List[FileInfo] = []
    pending: List[Tuple[Path, os.stat_result, Optional[FileInfo], int]] = []
    conn = kwargs["conn"]
    recompute = kwargs["recompute"]
    seg_length = kwargs["seg_length"]
    segwin_sliding = kwargs["segwin_sliding"]
    slide_step = kwargs["slide_step"]
    slide_max_slices = kwargs["slide_max_slices"]
    include_trim_head = kwargs["include_trim_head"]
    aggressive_fuzzy = kwargs["aggressive_fuzzy"]
    no_fp = kwargs["no_fp"]
    no_segwin = kwargs["no_segwin"]
    hash_mode = kwargs["hash_mode"]
    shutdown = kwargs["shutdown"]
    verbose = kwargs.get("verbose", True)

    next_id = _next_file_id(conn)
    discovered = 0
    log_path = root / "_DEDUP_SCAN_LOG.txt"

    def log_scan_entry(path: Path, status: str):
        try:
            ts = _dt.datetime.now().isoformat()
            with open(log_path, "a") as f:
                f.write(f"{ts}\t{path}\t{status}\n")
        except Exception:
            # Logging must not crash the dedupe run
            pass
        heartbeat(path)

    # Precompute already cached files with valid size/mtime for resuming
    if shutdown.should_stop():
        log("Stop requested — skipping new tasks submission.")
        pending = []
    already_cached = 0
    ticker_interval = 100
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        if shutdown.should_stop():
            break
        dirnames[:] = [
            name for name in dirnames if not name.upper().startswith("_TRASH_DUPES")
        ]
        for filename in sorted(filenames):
            if shutdown.should_stop():
                break
            if not filename.lower().endswith('.flac'):
                continue  # Ignore non-FLAC files entirely
            path = Path(dirpath) / filename
            heartbeat(path)
            discovered += 1
            if discovered % ticker_interval == 0:
                log(f"Progress: {discovered} files processed...")
            path_str = path.as_posix()
            if not os.path.exists(path_str) or not os.path.isfile(path_str):
                log(f"SKIP (missing): {path}")
                log_scan_entry(path, "SKIPPED")
                heartbeat(path)
                continue
            try:
                stat_info = os.stat(path_str)
            except FileNotFoundError:
                log(f"SKIP (missing): {path}")
                log_scan_entry(path, "SKIPPED")
                heartbeat(path)
                continue

            cached = load_file_from_db(conn, path)
            if cached:
                load_slide_hashes(conn, cached.id, cached.segments)

            # If cached, up-to-date, and not recomputing, skip and reuse
            if (
                cached
                and not recompute
                and cached.size_bytes == stat_info.st_size
                and abs(cached.mtime - stat_info.st_mtime) < 1
            ):
                if verbose:
                    log("  Using cached analysis")
                files.append(cached)
                log_scan_entry(path, "CACHED")
                already_cached += 1
                heartbeat(path)
                continue

            file_id = cached.id if cached else next_id
            if not cached:
                next_id += 1

            pending.append((path, stat_info, cached, file_id))

    log(f"Resuming from previous scan: {already_cached} files already analyzed")
    if verbose:
        log(f"Discovered {discovered} .flac files under {root}")

    def analyze(task: Tuple[Path, os.stat_result, Optional[FileInfo], int]) -> Optional[FileInfo]:
        path, stat_info, cached, file_id = task
        if shutdown.should_stop():
            return cached

        heartbeat(path)
        info = FileInfo(
            id=file_id,
            path=path,
            inode=stat_info.st_ino,
            size_bytes=stat_info.st_size,
            mtime=stat_info.st_mtime,
        )
        info.lossless = True

        metadata = probe_ffprobe(path)
        if metadata:
            info.codec = metadata.get("codec") or "flac"
            info.duration = metadata.get("duration")
            info.bitrate_kbps = metadata.get("bitrate_kbps")
            stream_md5 = metadata.get("stream_md5")
            if stream_md5:
                info.stream_md5 = stream_md5

        md5 = compute_metaflac_md5(path)
        if md5:
            info.stream_md5 = md5
            info.exact_key_type = "stream_md5"

        if hash_mode == "file" or not info.stream_md5:
            pcm_sha1 = compute_pcm_sha1(path)
            if pcm_sha1:
                info.pcm_sha1 = pcm_sha1
                info.exact_key_type = "pcm_sha1"

        if not info.codec:
            info.codec = "flac"

        if not no_fp:
            fp, fp_hash = compute_fingerprint(path)
            info.fingerprint = fp
            info.fingerprint_hash = fp_hash
            if verbose:
                if fp:
                    log(f"  Fingerprint computed for {path}")
                else:
                    log(f"  Fingerprint unavailable for {path}")

        if no_segwin:
            info.segments = SegmentHashes()
        else:
            info.segments = compute_segment_hashes(
                path,
                info.duration,
                seg_length,
                segwin_sliding,
                slide_step,
                slide_max_slices,
                include_trim_head,
            )
            if verbose:
                if (
                    info.segments.head
                    or info.segments.middle
                    or info.segments.tail
                    or info.segments.slide_hashes
                ):
                    log(f"  Segment hashes computed for {path}")
                else:
                    log(f"  Segment hashes unavailable for {path}")

        info.fuzzy_key = build_fuzzy_key(path, aggressive_fuzzy)
        info.fuzzy_duration = info.duration

        info.healthy, info.health_note = check_health(path)
        if verbose:
            log(
                f"  Health check {info.healthy if info.healthy is not None else 'unknown'}"
                f" via {info.health_note or 'n/a'}"
            )

        # Enhanced skip logic for broken files
        # We still want to cache metadata for "broken" files so subsequent runs
        # count them as already analyzed (and don't keep re-testing forever).
        if skip_broken and info.healthy is False:
            broken_log = root / "_BROKEN_FILES.txt"
            try:
                with open(broken_log, "a") as f:
                    ts = _dt.datetime.now().isoformat()
                    hn = info.health_note or ""
                    f.write(f"{ts}\t{path}\t{hn}\n")
            except Exception:
                # don't let logging errors interrupt the run
                pass
            append_broken_playlist(path)
            log("Added broken file to playlist")
            log("Skipping broken file (cached metadata)")
            # Do not early-return None; return the populated info so the outer loop
            # will upsert it into the DB and future runs will treat it as cached.
            return info

        return info

    def print_progress(completed, total, width=50):
        global last_timestamp_color
        percent = completed / total if total > 0 else 0
        color = last_timestamp_color
        print(f"\r{color}{completed}/{total}\033[0m \033[1;37m({percent:.1%})\033[0m", end='', flush=True)

    if pending:
        import time
        max_workers = max(1, workers)
        total_files = len(pending)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(analyze, task): task[0] for task in pending
            }
            print(f"\033[36m[DIAG] Submitted {len(future_map)} tasks to ThreadPoolExecutor\033[0m", flush=True)
            for future in as_completed(future_map):
                if shutdown.should_stop():
                    log("Shutdown requested — cancelling remaining tasks.")
                    for f in future_map:
                        f.cancel()
                    break
                path = future_map[future]
                try:
                    # as_completed yields futures that are done; no per-future timeout needed
                    info = future.result()
                except Exception as exc:  # pragma: no cover - defensive
                    log(f"Error processing {path}: {exc}")
                    # Log as SKIPPED if processing failed
                    try:
                        log_scan_entry(path, "SKIPPED")
                    except Exception:
                        pass
                    continue
                if info is None:
                    # Log as SKIPPED if no info returned
                    try:
                        log_scan_entry(path, "SKIPPED")
                    except Exception:
                        pass
                    continue
                upsert_file(conn, info)
                if skip_broken and info.healthy is False:
                    log("[DIAG] Upserted broken file to DB")
                insert_segments(conn, info.id, info.segments)
                store_file_signals(conn, info)
                files.append(info)
                log(f"Processed: {path.name}")
                try:
                    log_scan_entry(path, "PROCESSED")
                except Exception:
                    pass
                completed += 1
                print_progress(completed, total_files)
                if completed % 100 == 0 or completed == total_files:
                    print(f"[{time.strftime('%H:%M:%S')}] Processed {completed}/{total_files} files")
            print()  # End the progress bar line
            print("\033[32m[DIAG] All tasks completed.\033[0m", flush=True)

    # Stop the freeze detector watcher
    freeze_detector_stop.set()
    return files


def _next_file_id(conn: sqlite3.Connection) -> int:
    """Return the next available file identifier."""

    cursor = conn.execute("SELECT IFNULL(MAX(id), 0) FROM files")
    row = cursor.fetchone()
    return (row[0] or 0) + 1


def record_run(
    conn: sqlite3.Connection, root: Path, dry_run: bool, options: Dict[str, object]
) -> int:
    """Insert a run record and return its identifier."""

    now = _dt.datetime.now(_dt.UTC).isoformat()
    cursor = conn.execute(
        """
        INSERT INTO runs (started_at, root, options_json, dry_run)
        VALUES (?, ?, ?, ?)
        """,
        (now, root.as_posix(), json.dumps(options), int(dry_run)),
    )
    conn.commit()
    return cursor.lastrowid


def finalize_run(conn: sqlite3.Connection, run_id: int) -> None:
    """Update the run record with the finishing timestamp."""

    now = _dt.datetime.now(_dt.UTC).isoformat()
    conn.execute("UPDATE runs SET finished_at=? WHERE id=?", (now, run_id))
    conn.commit()


def persist_groups(conn: sqlite3.Connection, run_id: int, groups: Sequence[GroupResult]) -> None:
    """Persist deduplication groups in the database."""

    conn.execute("DELETE FROM groups WHERE run_id=?", (run_id,))
    conn.commit()

    for group in groups:
        cursor = conn.execute(
            """
            INSERT INTO groups (run_id, group_key, method, keeper_file_id)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, group.key, group.method, group.keeper.id),
        )
        group_id = cursor.lastrowid
        entries = []


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dedupe FLAC files using database index",
    )
    parser.add_argument(
        "--root",
        default="/Volumes/dotad/MUSIC",
        help="Root directory to scan (default: /Volumes/dotad/MUSIC)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually move duplicate files to trash directory",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="Log additional progress information",
    )
    parser.add_argument(
        "--fp-sim-ratio",
        type=float,
        default=0.62,
        help="Minimum similarity ratio for fingerprint grouping",
    )
    parser.add_argument(
        "--fp-sim-shift",
        type=int,
        default=25,
        help="Maximum absolute fingerprint shift for similarity",
    )
    parser.add_argument(
        "--fp-sim-min-overlap",
        type=int,
        default=50,
        help="Minimum overlapping frames for fingerprint similarity",
    )
    parser.add_argument(
        "--segwin-min-matches",
        type=int,
        default=3,
        help="Required number of matching segments for SEGWIN grouping",
    )
    parser.add_argument(
        "--fuzzy-seconds",
        type=float,
        default=2.0,
        help="Duration tolerance for fuzzy filename matching",
    )
    parser.add_argument(
        "--trash-dir",
        type=str,
        help="Optional custom directory for moving duplicate losers"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run mode even if --commit is provided"
    )
    return parser.parse_args(argv)


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by :func:`main` and unit tests."""

    args = parse_args(argv)

    root = Path(args.root).expanduser()
    root_path = root.as_posix()
    if not os.path.exists(root_path) or not os.path.isdir(root_path):
        raise SystemExit(f"Root directory {root} does not exist")

    db_path = root / "_DEDUP_INDEX.db"
    if not db_path.exists():
        raise SystemExit(f"Database {db_path} does not exist. Run scan first.")

    conn = sqlite3.connect(db_path.as_posix(), timeout=30)
    ensure_schema(conn)

    run_id = record_run(conn, root, not args.commit, {})

    try:
        files = load_all_files_from_db(conn)

        if args.verbose:
            log(f"Loaded {len(files)} files from database for deduplication…")

        groups = build_groups(
            files=files,
            fp_sim_ratio=args.fp_sim_ratio,
            fp_sim_shift=args.fp_sim_shift,
            fp_sim_min_overlap=args.fp_sim_min_overlap,
            use_fingerprint=True,  # Assume fingerprints are computed
            use_segwin=True,
            segwin_min_matches=args.segwin_min_matches,
            use_slide=True,
            fuzzy_duration_tol=args.fuzzy_seconds,
        )

        if args.verbose:
            log(f"Formed {len(groups)} duplicate groups")

        persist_groups(conn, run_id, groups)

        timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        trash_dir = Path(args.trash_dir).expanduser() if args.trash_dir else (root / f"_TRASH_DUPES_{timestamp}")
        report_path = root / f"_DEDUP_REPORT_{timestamp}.csv"

        write_csv(report_path, groups, trash_dir, args.commit)

        if args.commit and not args.dry_run:
            move_duplicates(groups, trash_dir)
        else:
            log("Dry run mode: no files moved")

        log(f"CSV report written to {report_path}")
        log(f"Trash directory: {trash_dir}")
    finally:
        finalize_run(conn, run_id)
        conn.close()

    return 0


def main() -> None:
    """Console script entry point."""

    try:
        sys.exit(run())
    except KeyboardInterrupt:
        log("Interrupted")
        sys.exit(1)


if __name__ == "__main__":
    main()
