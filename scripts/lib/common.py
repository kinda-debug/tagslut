"""Common utilities shared by flac_scan and flac_dedupe."""

from __future__ import annotations

__all__ = [
    "CMD_TIMEOUT",
    "DECODE_TIMEOUT",
    "DIAGNOSTICS",
    "DB_SCHEMA_VERSION",
    "CommandError",
    "DiagnosticsManager",
    "FileInfo",
    "GroupResult",
    "SegmentHashes",
    "active_ffmpeg_pgids",
    "active_pgid_lock",
    "build_fuzzy_key",
    "check_health",
    "colorize_path",
    "compute_fingerprint",
    "compute_metaflac_md5",
    "compute_pcm_sha1",
    "compute_segment_hash",
    "compute_segment_hashes",
    "ensure_directory",
    "ensure_schema",
    "fingerprint_similarity",
    "freeze_detector_stop",
    "gay_flag_colors",
    "heartbeat",
    "human_size",
    "insert_fp_bands",
    "insert_segments",
    "is_tool_available",
    "last_progress_file",
    "last_progress_timestamp",
    "load_all_files_from_db",
    "load_file_from_db",
    "load_slide_hashes",
    "log",
    "log_progress",
    "log_skip",
    "normalize_filename",
    "parse_fpcalc_output",
    "progress_color_index",
    "progress_update_lock",
    "progress_word_offset",
    "probe_ffprobe",
    "register_active_pgid",
    "run_command",
    "scan_processed_count",
    "scan_progress_lock",
    "scan_skipped_count",
    "scan_total_files",
    "sha1_hex",
    "store_file_signals",
    "timestamp_color_index",
    "unregister_active_pgid",
    "upsert_file",
    "append_broken_playlist_entry",
    "load_broken_playlist_set",
    "start_watchdog_thread",
    "start_freeze_detector_watcher",
]


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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# For base64 fingerprint decoding
import base64
import struct
import time

# Freeze detector state
last_progress_timestamp = time.time()
last_progress_file = None
freeze_detector_stop = threading.Event()
# Track ffmpeg process groups spawned by this process so the freeze detector
# can target only those groups instead of issuing a global pkill. Use a lock
# to synchronize access from worker threads and the watcher thread.
active_ffmpeg_pgids: Set[int] = set()
active_pgid_lock = threading.Lock()


def register_active_pgid(pgid: int) -> None:
    try:
        with active_pgid_lock:
            active_ffmpeg_pgids.add(int(pgid))
    except (ValueError, TypeError):
        # invalid pgid provided or not coercible to int
        pass


def unregister_active_pgid(pgid: int) -> None:
    try:
        with active_pgid_lock:
            active_ffmpeg_pgids.discard(int(pgid))
    except (ValueError, TypeError):
        # ignore invalid inputs
        pass


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
    "\033[35m",  # Purple
]

# Shared diagnostics manager configured at runtime
DIAGNOSTICS: Optional[DiagnosticsManager] = None

# Default timeouts (seconds); overridable via CLI
CMD_TIMEOUT: int = 45  # fpcalc, flac -t, ffprobe, metaflac
DECODE_TIMEOUT: int = (
    30  # ffmpeg streaming/decoding (PCM hash, segments) - reduced default to avoid long stalls
)


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
        dir_part = "/".join(parts[:-1]) + "/"
        file_part = parts[-1]
        return f"\033[36m{dir_part}\033[0m\033[37m{file_part}\033[0m"  # cyan for dir, white for file
    except (TypeError, OSError, ValueError):
        # Be defensive but avoid swallowing BaseException
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
    elif (
        "Skipping" in message or "broken" in message or "quarantine" in message.lower()
    ):
        message_color = "\033[31m"  # red for skips/broken
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
        print(
            f"[{timestamp}] Progress: {processed}/{total} ({percent:.1f}%) — {path.name} | Skipped: {skipped} files"
        )
    else:
        print(
            f"[{timestamp}] Progress: {processed}/{total} ({percent:.1f}%) — {path.name}"
        )
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
    print(
        f"[{timestamp}] Skipped: {skipped} files so far — {path.name} | Progress: {processed}/{total}"
    )
    heartbeat(path)


def is_tool_available(tool: str) -> bool:
    """Return ``True`` when *tool* is present on ``PATH`` and executable."""

    return shutil.which(tool) is not None


def sha1_hex(data: bytes) -> str:
    """Return the hexadecimal SHA1 digest of *data*."""
    return hashlib.sha1(data).hexdigest()


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
            fallback_base = Path(
                os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
            )
            fallback = fallback_base / "dedupe_diagnostics"
            ensure_directory(fallback)
            log(
                "Diagnostic root %s unavailable; using %s instead"
                % (candidate.as_posix(), fallback.as_posix())
            )
            return fallback

    def _kind_dir(self, kind: str) -> Path:
        path = self.root / kind
        ensure_directory(path)
        return path

    def _safe_component(self, source: Path) -> str:
        base = source.name or "root"
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:48] or "entry"
        digest = hashlib.sha1(source.as_posix().encode("utf-8")).hexdigest()[:8]
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
        dump_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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

    def record_watchdog(
        self, message: str, context: Optional[str] = None
    ) -> Optional[Path]:
        """Persist watchdog/freeze diagnostic entries."""

        if not self.dump_watchdog:
            return None
        metadata = {"context": context} if context else {}
        return self._write_json(
            "watchdog", Path("/watchdog"), "message", message, **metadata
        )

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
        pgid = None
        try:
            pgid = os.getpgid(process.pid)
            register_active_pgid(pgid)
        except OSError:
            pgid = None
    except FileNotFoundError as exc:
        raise CommandError(str(exc)) from exc
    try:
        stdout, stderr = process.communicate(timeout=effective_timeout)
    except subprocess.TimeoutExpired:
        # Kill the process group if possible; otherwise try killing the process
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            try:
                process.kill()
            except OSError:
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
            except OSError:
                try:
                    process.kill()
                except OSError:
                    pass

        raise CommandError(f"Timeout executing {' '.join(command)}")
    finally:
        try:
            if pgid is not None:
                unregister_active_pgid(pgid)
        except OSError:
            pass

    if process.returncode != 0:
        cmd_str = " ".join(command)
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
        output = run_command(
            ["metaflac", "--show-md5sum", str(path)], timeout=CMD_TIMEOUT
        )
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

    pgid = None
    try:
        try:
            pgid = os.getpgid(process.pid)
            register_active_pgid(pgid)
        except OSError:
            pgid = None

        import time

        deadline = time.time() + DECODE_TIMEOUT
        digest = hashlib.sha1()
        assert process.stdout is not None
        stderr_chunks: List[bytes] = []
        while True:
            if time.time() > deadline:
                # Try to gracefully terminate the whole process group, then force-kill
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except OSError:
                    try:
                        process.kill()
                    except OSError:
                        pass

                if process.stdout:
                    try:
                        process.stdout.close()
                    except OSError:
                        pass

                try:
                    process.wait()
                except OSError:
                    pass

                if process.stderr is not None:
                    try:
                        stderr_chunks.append(process.stderr.read() or b"")
                        process.stderr.close()
                    except OSError:
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

        # close stdout and wait for process; stderr collect done after
        try:
            if process.stdout:
                process.stdout.close()
        except OSError:
            pass
        try:
            process.wait()
        except OSError:
            pass
        stderr_text = ""
        if process.stderr is not None:
            try:
                stderr_chunks.append(process.stderr.read() or b"")
                process.stderr.close()
            except OSError:
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
    finally:
        try:
            if pgid is not None:
                unregister_active_pgid(pgid)
        except OSError:
            pass


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
        # Launch ffmpeg in its own process group so we can kill children if stalled.
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    pgid = None
    try:
        try:
            pgid = os.getpgid(process.pid)
            register_active_pgid(pgid)
        except OSError:
            pgid = None

        import time

        deadline = time.time() + DECODE_TIMEOUT
        digest = hashlib.sha1()
        assert process.stdout is not None
        stderr_chunks: List[bytes] = []
        while True:
            if time.time() > deadline:
                try:
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)
                except OSError:
                    try:
                        process.kill()
                    except OSError:
                        pass
                if process.stdout:
                    try:
                        process.stdout.close()
                    except OSError:
                        pass
                process.wait()
                if process.stderr is not None:
                    try:
                        stderr_chunks.append(process.stderr.read() or b"")
                        process.stderr.close()
                    except OSError:
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

        try:
            if process.stdout:
                process.stdout.close()
        except OSError:
            pass
        try:
            process.wait()
        except OSError:
            pass
        stderr_text = ""
        if process.stderr is not None:
            try:
                stderr_chunks.append(process.stderr.read() or b"")
                process.stderr.close()
            except OSError:
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
    finally:
        try:
            if pgid is not None:
                unregister_active_pgid(pgid)
        except OSError:
            pass


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


def _coerce_fingerprint_sequence(values: Iterable[Any]) -> Optional[List[int]]:
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

    def _finalize(
        values: Optional[List[int]],
    ) -> Tuple[Optional[List[int]], Optional[str]]:
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
        fingerprint = _coerce_fingerprint_sequence(
            part for part in raw.split(",") if part
        )
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
                DIAGNOSTICS.record_fpcalc(
                    path, "", command, success=False, error=str(exc)
                )
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


def upsert_file(conn: sqlite3.Connection, info: FileInfo) -> None:
    """Insert or update a :class:`FileInfo` in the database."""

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
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


def insert_segments(
    conn: sqlite3.Connection, file_id: int, segments: SegmentHashes
) -> None:
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


def load_slide_hashes(
    conn: sqlite3.Connection, file_id: int, segments: SegmentHashes
) -> None:
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
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
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


def insert_fp_bands(
    conn: sqlite3.Connection, file_id: int, fingerprint: Sequence[int]
) -> None:
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


def load_broken_playlist_set(broken_playlist_path: Optional[str]) -> Set[str]:
    """Return the set of entries already present in *broken_playlist_path*.

    The function tolerates missing files and returns an empty set when no
    playlist is configured.
    """
    seen: Set[str] = set()
    if not broken_playlist_path:
        return seen
    try:
        if os.path.exists(broken_playlist_path):
            with open(broken_playlist_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        seen.add(line)
    except (OSError, UnicodeDecodeError):
        # Best-effort: do not fail scans due to playlist IO errors.
        pass
    return seen


def append_broken_playlist_entry(
    broken_playlist_path: Optional[str], seen_set: Set[str], path: Path
) -> None:
    """Append *path* to *broken_playlist_path* if not already recorded.

    Updates *seen_set* in-place.
    """
    if not broken_playlist_path:
        return
    try:
        abs_path = str(path.resolve())
    except (OSError, RuntimeError):
        try:
            abs_path = str(path)
        except (OSError, RuntimeError):
            return
    if abs_path in seen_set:
        return
    try:
        Path(broken_playlist_path).expanduser().parent.mkdir(
            parents=True, exist_ok=True
        )
    except OSError:
        pass
    try:
        with open(broken_playlist_path, "a", encoding="utf-8") as fh:
            fh.write(abs_path + "\n")
        seen_set.add(abs_path)
    except OSError:
        # Never raise from playlist writes
        pass


def start_watchdog_thread(
    timeout: int = 300,
    shutdown: Optional[Any] = None,
    stop_event: Optional[threading.Event] = None,
) -> threading.Thread:
    """Start a background watchdog thread that requests shutdown on stall.

    The watchdog checks the shared ``last_progress_timestamp`` and will set
    ``freeze_detector_stop`` and the optional ``shutdown`` object's
    ``_stop_event`` when a stall is detected.
    """

    t_stop = stop_event or freeze_detector_stop

    def _watch() -> None:
        import time

        while not t_stop.is_set():
            time.sleep(5)
            if time.time() - last_progress_timestamp > timeout:
                print(
                    f"[WATCHDOG] No progress for {timeout} seconds. Requesting shutdown.",
                    flush=True,
                )
                if DIAGNOSTICS is not None:
                    DIAGNOSTICS.record_watchdog(
                        f"No progress for {timeout} seconds", context=last_progress_file
                    )
                try:
                    t_stop.set()
                except AttributeError:
                    # Defensive: stop_event may not expose set()
                    pass
                try:
                    stop = getattr(shutdown, "_stop_event", None)
                    if stop is not None:
                        stop.set()
                except Exception:
                    # Defensive: ignore any errors when attempting to set
                    # the shutdown object's internal stop event.
                    pass
                t_stop.set()
                return

    thr = threading.Thread(target=_watch, daemon=True)
    thr.start()
    return thr


def start_freeze_detector_watcher(
    root: Optional[Path] = None,
    auto_quarantine: bool = False,
    kill_in_terminal: bool = True,
) -> threading.Thread:
    """Start a freeze detector watcher thread.

    The watcher attempts targeted kills of tracked ffmpeg process groups and
    falls back to global pkill/killall when needed. If *auto_quarantine* is
    True and *root* is provided, frozen files will be moved under
    ``{root}/_BROKEN``.
    """

    def _watch(quarantine_dir: Optional[str]) -> None:
        import time

        while not freeze_detector_stop.is_set():
            time.sleep(5)
            now = time.time()
            if now - last_progress_timestamp > 30 and last_progress_file:
                print(
                    f"[FREEZE DETECTOR] Triggered: no progress for 30s on {last_progress_file}",
                    flush=True,
                )
                log(f"WARNING: No progress for 30s. Last file: {last_progress_file}")
                if DIAGNOSTICS is not None:
                    DIAGNOSTICS.record_watchdog(
                        "Freeze detector triggered", context=last_progress_file
                    )
                try:
                    # First prefer targeted kills for pgids we know we spawned.
                    with active_pgid_lock:
                        pgids = list(active_ffmpeg_pgids)

                    if pgids:
                        log(
                            f"Freeze detector: attempting targeted kill of {len(pgids)} ffmpeg pgid(s)"
                        )
                        for pgid in pgids:
                            try:
                                os.killpg(pgid, signal.SIGTERM)
                            except OSError:
                                pass
                        time.sleep(0.5)
                        for pgid in pgids:
                            try:
                                os.killpg(pgid, 0)
                            except OSError:
                                continue
                            try:
                                os.killpg(pgid, signal.SIGKILL)
                            except OSError:
                                pass
                        log("Freeze detector: targeted kill completed")
                    else:
                        pkill_path = shutil.which("pkill")
                        killall_path = shutil.which("killall")
                        if kill_in_terminal and sys.platform == "darwin" and pkill_path:
                            script = (
                                f"{pkill_path} ffmpeg; echo 'pkill (TERM) sent'; exit"
                            )
                            osa_cmd = [
                                "osascript",
                                "-e",
                                f'tell application "Terminal" to do script "{script}"',
                            ]
                            subprocess.run(osa_cmd, check=False, timeout=5)
                            log("Issued pkill (TERM) ffmpeg in a new Terminal window")
                        else:
                            if pkill_path:
                                subprocess.run(
                                    [pkill_path, "ffmpeg"], check=False, timeout=5
                                )
                                log("Sent TERM to stalled ffmpeg processes (pkill)")
                            elif killall_path:
                                subprocess.run(
                                    [killall_path, "ffmpeg"], check=False, timeout=5
                                )
                                log("Sent TERM to stalled ffmpeg processes (killall)")
                            else:
                                log(
                                    "No pkill/killall found in PATH; cannot run global pkill fallback"
                                )
                except (OSError, subprocess.SubprocessError) as e:
                    log(f"Failed to kill ffmpeg: {e}")
                if quarantine_dir and os.path.exists(last_progress_file):
                    try:
                        os.makedirs(quarantine_dir, exist_ok=True)
                        dest = os.path.join(
                            quarantine_dir, os.path.basename(last_progress_file)
                        )
                        shutil.move(last_progress_file, dest)
                        log(f"Moved frozen file to quarantine: {dest}")
                    except OSError as e:
                        log(f"Failed to quarantine file: {e}")
                freeze_detector_stop.set()

    quarantine = None
    if auto_quarantine and root is not None:
        quarantine = os.path.join(str(root), "_BROKEN")

    t = threading.Thread(target=_watch, args=(quarantine,), daemon=True)
    t.start()
    return t


# CSV output headers used by both scan and dedupe
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


def plan_trash_destination(trash_dir: Path, file_path: Path) -> Path:
    """Return the destination inside the trash directory preserving structure."""

    try:
        rel = file_path.relative_to(file_path.anchor)
    except ValueError:
        rel = Path(file_path.name)
    return trash_dir.joinpath(rel)


def move_duplicates(groups: Sequence[GroupResult], trash_dir: Path) -> None:
    """Move loser files to the trash directory (robust: logs and continues on errors)."""

    ensure_directory(trash_dir)
    for group in groups:
        for file in group.losers:
            dest = plan_trash_destination(trash_dir, file.path)
            ensure_directory(dest.parent)
            try:
                if not file.path.exists():
                    log(f"Missing (skipping): {file.path}")
                    continue
                log(f"Moving {file.path} -> {dest}")
                shutil.move(file.path.as_posix(), dest.as_posix())
            except FileNotFoundError:
                log(f"Missing during move (skipping): {file.path}")
                continue
            except OSError as exc:
                log(f"Failed to move {file.path} -> {dest}: {exc}")
                try:
                    errlog = trash_dir.parent / "_DEDUP_MOVE_ERRORS.txt"
                    with errlog.open("a", encoding="utf-8") as fh:
                        fh.write(
                            f"{_dt.datetime.now().isoformat()}\t{file.path}\t{dest}\t{exc}\n"
                        )
                except OSError:
                    pass
