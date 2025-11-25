"""FLAC audio deduplicator with persistent signal cache.

This module provides a macOS-friendly, dependency-free command line utility
that scans a music library for FLAC duplicates.  The implementation closely
follows the requirements from the prompt and persists all extracted audio
signals in a SQLite database so that subsequent runs can reuse previously
computed information.  The script prefers external multimedia binaries when
available (``ffprobe``, ``ffmpeg``, ``flac``, ``metaflac`` and ``fpcalc``) but it
operates gracefully when a tool is missing by skipping the associated
deduplication stage.

The deduplication pipeline evaluates several progressively fuzzy stages:

``EXACT``
    Uses FLAC stream MD5 or a PCM SHA1 hash.

``FPRINT``
    Groups by the chromaprint hash when fingerprints are available.

``FPRINT_SIM``
    Performs a tolerant comparison between fingerprints and groups files that
    are sufficiently similar.

``SEGWIN``
    Hashes PCM excerpts from the head, middle and tail of the track.

``SEGWIN_SLIDE``
    Optional sliding-window segment hashing for additional confidence.

``FUZZY``
    Uses a filename-derived fuzzy key combined with duration tolerance.

Every group elects a winner according to file health, losslessness, duration,
bitrate and modification time.  Duplicates are moved to a timestamped trash
directory when ``--commit`` is provided; otherwise a dry-run report is
generated.

The module avoids third-party Python packages, instead relying solely on the
standard library.  All public functions include docstrings and type hints to
aid future maintenance.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import textwrap
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


###############################################################################
# Utility helpers
###############################################################################


def log(message: str) -> None:
    """Print a human friendly timestamped log message."""

    timestamp = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")


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


###############################################################################
# External command helpers
###############################################################################


class CommandError(RuntimeError):
    """Raised when an external command fails."""


def run_command(command: Sequence[str], timeout: Optional[int] = None) -> str:
    """Execute *command* and return ``stdout``.

    The function raises :class:`CommandError` on non-zero return codes.  When a
    timeout occurs the subprocess is killed and the same exception is raised.
    """

    try:
        completed = subprocess.run(
            list(command),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on system
        raise CommandError(str(exc)) from exc
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - rare
        raise CommandError(f"Timeout executing {' '.join(command)}") from exc

    if completed.returncode != 0:
        raise CommandError(
            f"Command {' '.join(command)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout


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
        output = run_command(cmd)
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
        output = run_command(["metaflac", "--show-md5sum", str(path)])
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
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    digest = hashlib.sha1(usedforsecurity=False)
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(65536)
        if not chunk:
            break
        digest.update(chunk)

    process.stdout.close()
    process.wait()
    if process.returncode != 0:
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
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:  # pragma: no cover - environment dependent
        return None

    digest = hashlib.sha1(usedforsecurity=False)
    assert process.stdout is not None
    while True:
        chunk = process.stdout.read(65536)
        if not chunk:
            break
        digest.update(chunk)

    process.stdout.close()
    process.wait()
    if process.returncode != 0:
        return None
    return digest.hexdigest()


def compute_segment_hashes(
    path: Path,
    duration: Optional[float],
    seg_length: float,
    slide_step: float,
    slide_count: int,
) -> SegmentHashes:
    """Compute hashes for head/middle/tail and sliding window excerpts."""

    hashes = SegmentHashes()
    if duration is None:
        return hashes

    duration = max(duration, 0.0)
    seg_length = min(seg_length, duration)
    if seg_length <= 0:
        return hashes

    hashes.head = compute_segment_hash(path, 0.0, seg_length)
    mid_start = max((duration - seg_length) / 2.0, 0.0)
    hashes.middle = compute_segment_hash(path, mid_start, seg_length)
    tail_start = max(duration - seg_length, 0.0)
    hashes.tail = compute_segment_hash(path, tail_start, seg_length)

    # Trimmed head removes the first second to skip common silences.
    trim_start = min(1.0, max(duration - seg_length, 0.0))
    hashes.trimmed_head = compute_segment_hash(path, trim_start, seg_length)

    if slide_count > 0 and slide_step > 0:
        for index in range(slide_count):
            start = slide_step * index
            if start + seg_length > duration:
                break
            segment_hash = compute_segment_hash(path, start, seg_length)
            if segment_hash:
                hashes.slide_hashes.append(segment_hash)

    return hashes


def parse_fpcalc_output(output: str) -> Tuple[Optional[List[int]], Optional[str]]:
    """Parse ``fpcalc`` output and return the fingerprint and its hash."""

    fingerprint: Optional[List[int]] = None
    if not output.strip():
        return (None, None)

    try:
        data = json.loads(output)
        if isinstance(data, dict) and "fingerprint" in data:
            if isinstance(data["fingerprint"], list):
                fingerprint = [int(v) for v in data["fingerprint"]]
            elif isinstance(data["fingerprint"], str):
                fingerprint = [int(v) for v in data["fingerprint"].split(",") if v]
    except json.JSONDecodeError:
        for line in output.splitlines():
            if line.startswith("FINGERPRINT="):
                raw = line.split("=", 1)[1].strip()
                fingerprint = [int(v) for v in raw.split(",") if v]
                break

    if not fingerprint:
        return (None, None)

    hash_hex = sha1_hex(",".join(str(v) for v in fingerprint).encode("utf-8"))
    return (fingerprint, hash_hex)


def compute_fingerprint(path: Path) -> Tuple[Optional[List[int]], Optional[str]]:
    """Compute the chromaprint fingerprint using ``fpcalc``."""

    if not is_tool_available("fpcalc"):
        return (None, None)
    try:
        output = run_command(["fpcalc", "-json", str(path)])
    except CommandError:
        try:
            output = run_command(["fpcalc", str(path)])
        except CommandError:
            return (None, None)
    return parse_fpcalc_output(output)


def check_health(path: Path) -> Tuple[Optional[bool], Optional[str]]:
    """Check file health via ``flac -t`` or ``ffmpeg`` decoding."""

    if is_tool_available("flac"):
        try:
            run_command(["flac", "-s", "-t", str(path)])
            return (True, "flac -t")
        except CommandError as exc:
            return (False, f"flac -t failed: {exc}")

    if is_tool_available("ffmpeg"):
        cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"]
        try:
            run_command(cmd)
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

    now = _dt.datetime.utcnow().isoformat()
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
    now = _dt.datetime.utcnow().isoformat()
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
    fp_sim_overlap: int,
    enable_slide: bool,
    fuzzy_duration_tol: float,
) -> List[GroupResult]:
    """Group files using the staged deduplication pipeline."""

    by_id = {file.id: file for file in files}
    remaining = set(by_id.keys())
    groups: List[GroupResult] = []

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
    used_pairs: set[Tuple[int, int]] = set()
    for i, file_a in enumerate(fp_candidates):
        for file_b in fp_candidates[i + 1 :]:
            pair = tuple(sorted((file_a.id, file_b.id)))
            if pair in used_pairs:
                continue
            ratio, shift, overlap = fingerprint_similarity(
                file_a.fingerprint or [],
                file_b.fingerprint or [],
                fp_sim_shift,
                fp_sim_overlap,
            )
            if ratio >= fp_sim_ratio:
                register_group(
                    key=f"FPS:{file_a.id}:{file_b.id}",
                    method=f"FPRINT_SIM(r={ratio:.2f},s={shift})",
                    members=[file_a, file_b],
                )
                used_pairs.add(pair)

    # Stage D: segment windows head/mid/tail
    key_to_members = {}
    for file in files:
        if file.id not in remaining:
            continue
        key = (file.segments.head, file.segments.middle, file.segments.tail)
        if all(key):
            key_to_members.setdefault(key, []).append(file)
    for key, members in key_to_members.items():
        if len(members) > 1:
            register_group(
                key=f"SEG:{key[0]}:{key[1]}:{key[2]}", method="SEGWIN", members=members
            )

    # Stage E: sliding windows (optional)
    if enable_slide:
        slide_map: Dict[str, List[FileInfo]] = {}
        for file in files:
            if file.id not in remaining:
                continue
            for slide_hash in file.segments.slide_hashes:
                slide_map.setdefault(slide_hash, []).append(file)
        for key, members in slide_map.items():
            unique_members = {member.id: member for member in members}.values()
            if len(unique_members) > 1:
                register_group(
                    key=f"SLIDE:{key}",
                    method="SEGWIN_SLIDE",
                    members=list(unique_members),
                )

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

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._handler)

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _handler(self, signum, frame) -> None:  # type: ignore[override]
        log("Received SIGINT; finishing current work...")
        self._stop_event.set()


def scan_files(
    root: Path,
    conn: sqlite3.Connection,
    recompute: bool,
    seg_length: float,
    slide_step: float,
    slide_count: int,
    aggressive_fuzzy: bool,
    no_fp: bool,
    hash_mode: str,
    shutdown: GracefulShutdown,
) -> List[FileInfo]:
    """Walk the filesystem and return fresh :class:`FileInfo` instances."""

    files: List[FileInfo] = []
    next_id = _next_file_id(conn)
    for dirpath, dirnames, filenames in os.walk(root):
        if shutdown.should_stop():
            break
        dirnames[:] = [
            name for name in dirnames if not name.upper().startswith("_TRASH_DUPES")
        ]
        for filename in filenames:
            if shutdown.should_stop():
                break
            path = Path(dirpath) / filename
            if path.suffix.lower() != ".flac":
                continue
            stat_info = path.stat()
            cached = load_file_from_db(conn, path)
            if (
                cached
                and not recompute
                and cached.size_bytes == stat_info.st_size
                and abs(cached.mtime - stat_info.st_mtime) < 1
            ):
                load_slide_hashes(conn, cached.id, cached.segments)
                files.append(cached)
                continue

            file_id = cached.id if cached else next_id
            next_id = max(next_id, file_id + 1)
            info = FileInfo(
                id=file_id,
                path=path,
                inode=stat_info.st_ino,
                size_bytes=stat_info.st_size,
                mtime=stat_info.st_mtime,
            )

            metadata = probe_ffprobe(path)
            info.codec = metadata.get("codec") if metadata else None
            info.duration = metadata.get("duration") if metadata else None
            info.bitrate_kbps = metadata.get("bitrate_kbps") if metadata else None

            md5 = compute_metaflac_md5(path)
            if md5:
                info.stream_md5 = md5
                info.exact_key_type = "stream_md5"
            if not info.stream_md5 or hash_mode == "file":
                info.pcm_sha1 = compute_pcm_sha1(path)
                if info.pcm_sha1:
                    info.exact_key_type = "pcm_sha1"

            if not no_fp:
                fp, fp_hash = compute_fingerprint(path)
                info.fingerprint = fp
                info.fingerprint_hash = fp_hash

            info.segments = compute_segment_hashes(
                path,
                info.duration,
                seg_length,
                slide_step,
                slide_count,
            )

            info.fuzzy_key = build_fuzzy_key(path, aggressive_fuzzy)
            info.fuzzy_duration = info.duration

            info.healthy, info.health_note = check_health(path)

            upsert_file(conn, info)
            insert_segments(conn, info.id, info.segments)
            store_file_signals(conn, info)

            files.append(info)

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

    now = _dt.datetime.utcnow().isoformat()
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

    now = _dt.datetime.utcnow().isoformat()
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
        for member in [group.keeper] + group.losers:
            role = "keeper" if member == group.keeper else "loser"
            entries.append((group_id, member.id, role, None, None))
        conn.executemany(
            """
            INSERT INTO group_members (group_id, file_id, role, action, dest_path)
            VALUES (?, ?, ?, ?, ?)
            """,
            entries,
        )
    conn.commit()


###############################################################################
# CLI parsing and main entry point
###############################################################################


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Return parsed command line arguments."""

    parser = argparse.ArgumentParser(description="Deduplicate FLAC files with DB cache")
    parser.add_argument("--root", default="DD", help="Root directory to scan")
    parser.add_argument("--commit", action="store_true", help="Apply changes")
    parser.add_argument("--trash-dir", help="Override trash directory")
    parser.add_argument(
        "--report-csv",
        help="Override path for the CSV report",
    )
    parser.add_argument(
        "--hash-mode",
        choices=["auto", "file"],
        default="auto",
        help="Hashing mode (auto uses FLAC MD5 when available)",
    )
    parser.add_argument("--no-fp", action="store_true", help="Disable fingerprinting")
    parser.add_argument(
        "--fp-sim-ratio",
        type=float,
        default=0.62,
        help="Similarity ratio threshold for fingerprint comparisons",
    )
    parser.add_argument(
        "--fp-sim-shift",
        type=int,
        default=25,
        help="Maximum allowed fingerprint shift",
    )
    parser.add_argument(
        "--fp-sim-overlap",
        type=int,
        default=50,
        help="Minimum overlap for fingerprint similarity",
    )
    parser.add_argument(
        "--segwin-duration",
        type=float,
        default=15.0,
        help="PCM excerpt length used for segment hashing",
    )
    parser.add_argument(
        "--segwin-slide-step",
        type=float,
        default=30.0,
        help="Sliding window step size in seconds",
    )
    parser.add_argument(
        "--segwin-slide-count",
        type=int,
        default=5,
        help="Number of sliding window excerpts to compute",
    )
    parser.add_argument(
        "--fuzzy-duration-tol",
        type=float,
        default=2.0,
        help="Duration tolerance (seconds) for fuzzy matching",
    )
    parser.add_argument(
        "--fuzzy-aggressive",
        action="store_true",
        help="Aggressively strip remix/edit tokens from fuzzy keys",
    )
    parser.add_argument("--workers", type=int, default=1, help="Reserved for future use")
    parser.add_argument("--recompute", action="store_true", help="Recompute all signals")
    parser.add_argument(
        "--db",
        default=str(Path.home() / "Music" / "dedupe" / "dedupe.db"),
        help="SQLite database path",
    )
    return parser.parse_args(argv)


def run(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point used by :func:`main` and unit tests."""

    args = parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Root directory {root} does not exist")

    db_path = Path(args.db).expanduser()
    ensure_directory(db_path.parent)
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    shutdown = GracefulShutdown()
    shutdown.install()

    options = {
        "hash_mode": args.hash_mode,
        "no_fp": args.no_fp,
        "fp_sim_ratio": args.fp_sim_ratio,
        "fp_sim_shift": args.fp_sim_shift,
        "fp_sim_overlap": args.fp_sim_overlap,
        "segwin_duration": args.segwin_duration,
        "segwin_slide_step": args.segwin_slide_step,
        "segwin_slide_count": args.segwin_slide_count,
        "fuzzy_duration_tol": args.fuzzy_duration_tol,
        "fuzzy_aggressive": args.fuzzy_aggressive,
        "workers": args.workers,
        "recompute": args.recompute,
    }

    run_id = record_run(conn, root, not args.commit, options)

    files = scan_files(
        root=root,
        conn=conn,
        recompute=args.recompute,
        seg_length=args.segwin_duration,
        slide_step=args.segwin_slide_step,
        slide_count=args.segwin_slide_count,
        aggressive_fuzzy=args.fuzzy_aggressive,
        no_fp=args.no_fp,
        hash_mode=args.hash_mode,
        shutdown=shutdown,
    )

    groups = build_groups(
        files=files,
        fp_sim_ratio=args.fp_sim_ratio,
        fp_sim_shift=args.fp_sim_shift,
        fp_sim_overlap=args.fp_sim_overlap,
        enable_slide=args.segwin_slide_count > 0,
        fuzzy_duration_tol=args.fuzzy_duration_tol,
    )

    persist_groups(conn, run_id, groups)

    timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash_base = Path(args.trash_dir).expanduser() if args.trash_dir else root
    trash_dir = trash_base / f"_TRASH_DUPES_{timestamp}"
    report_path = (
        Path(args.report_csv).expanduser()
        if args.report_csv
        else root / f"_DEDUP_REPORT_{timestamp}.csv"
    )

    write_csv(report_path, groups, trash_dir, args.commit)

    if args.commit:
        move_duplicates(groups, trash_dir)

    finalize_run(conn, run_id)
    conn.close()

    log(f"CSV report written to {report_path}")
    log(f"Trash directory: {trash_dir}")
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
