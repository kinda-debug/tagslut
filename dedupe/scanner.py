"""Library scanning logic."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Iterator, Optional
import os
import unicodedata

from . import fingerprints, metadata, utils

LOGGER = logging.getLogger(__name__)

LIBRARY_TABLE = "library_files"


@dataclass(slots=True)
class ScanRecord:
    """Metadata collected for an audio file."""

    path: str
    size_bytes: int
    mtime: float
    checksum: str
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]
    tags_json: str
    fingerprint: Optional[str]
    fingerprint_duration: Optional[float]


@dataclass(slots=True)
class ScanConfig:
    """Configuration for :func:`scan_library`.

    Attributes:
        root: root path to scan
        database: sqlite database path
        include_fingerprints: whether to request Chromaprint fingerprints
        batch_size: number of files per DB upsert
        resume: skip files already indexed and unchanged
        resume_safe: like resume, but ensures batches with any scanned files are skipped safely
        show_progress: display a progress bar during scanning
    """

    root: Path
    database: Path
    include_fingerprints: bool = False
    batch_size: int = 100
    resume: bool = False
    resume_safe: bool = False
    nfd_normalise: bool = True
    show_progress: bool = False


def initialise_database(connection: sqlite3.Connection) -> None:
    """Ensure the SQLite schema exists."""

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LIBRARY_TABLE} (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            mtime REAL NOT NULL,
            checksum TEXT NOT NULL,
            duration REAL,
            sample_rate INTEGER,
            bit_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            tags_json TEXT,
            fingerprint TEXT,
            fingerprint_duration REAL
        )
        """
    )


def resolve_fingerprint_usage(include_requested: bool) -> bool:
    """Return ``True`` when Chromaprint fingerprints should be generated.

    Fingerprints are only generated when the caller explicitly requests them
    *and* ``fpcalc`` is available on the execution ``PATH``.  The helper keeps
    the gating logic in a single place so callers do not need to repeat the
    availability checks.
    """

    if not include_requested:
        return False
    if not fingerprints.is_fpcalc_available():
        LOGGER.info(
            "Chromaprint fingerprints requested but fpcalc not available; "
            "continuing without fingerprints",
        )
        return False
    LOGGER.info("Chromaprint fingerprints enabled for this scan")
    return True


def prepare_record(path: Path, include_fingerprints: bool) -> ScanRecord:
    """Collect metadata and optional fingerprint information for *path*."""
    meta = metadata.probe_audio(path)
    checksum = utils.compute_md5(path)
    fingerprint_result = (
        fingerprints.generate_chromaprint(path)
        if include_fingerprints
        else None
    )
    return ScanRecord(
        path=utils.normalise_path(unicodedata.normalize("NFC", str(path))),
        size_bytes=meta.size_bytes,
        mtime=path.stat().st_mtime,
        checksum=checksum,
        duration=meta.stream.duration,
        sample_rate=meta.stream.sample_rate,
        bit_rate=meta.stream.bit_rate,
        channels=meta.stream.channels,
        bit_depth=meta.stream.bit_depth,
        tags_json=json.dumps(meta.tags, sort_keys=True),
        fingerprint=(
            fingerprint_result.fingerprint if fingerprint_result else None
        ),
        fingerprint_duration=(
            fingerprint_result.duration if fingerprint_result else None
        ),
    )


def _iter_records(
    paths: Iterable[Path],
    include_fingerprints: bool,
) -> Iterator[ScanRecord]:
    for path in paths:
        try:
            yield prepare_record(path, include_fingerprints)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to scan %s: %s", path, exc)


def _upsert_batch(
    connection: sqlite3.Connection,
    records: Iterable[ScanRecord],
) -> None:
    connection.executemany(
        f"""
        INSERT INTO {LIBRARY_TABLE} (
            path,
            size_bytes,
            mtime,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            channels,
            bit_depth,
            tags_json,
            fingerprint,
            fingerprint_duration
        ) VALUES (
            :path,
            :size_bytes,
            :mtime,
            :checksum,
            :duration,
            :sample_rate,
            :bit_rate,
            :channels,
            :bit_depth,
            :tags_json,
            :fingerprint,
            :fingerprint_duration
        )
        ON CONFLICT(path) DO UPDATE SET
            size_bytes=excluded.size_bytes,
            mtime=excluded.mtime,
            checksum=excluded.checksum,
            duration=excluded.duration,
            sample_rate=excluded.sample_rate,
            bit_rate=excluded.bit_rate,
            channels=excluded.channels,
            bit_depth=excluded.bit_depth,
            tags_json=excluded.tags_json,
            fingerprint=excluded.fingerprint,
            fingerprint_duration=excluded.fingerprint_duration
        """,
        [asdict(record) for record in records],
    )


def scan_library(config: ScanConfig) -> int:
    """Scan ``config.root`` and populate ``config.database``."""
    utils.ensure_parent_directory(config.database)
    db = utils.DatabaseContext(config.database)
    start = time.time()
    total = 0
    include_fingerprints = resolve_fingerprint_usage(config.include_fingerprints)

    # Build an index of already-scanned files when resuming. We index by the
    # normalised path and record the size and mtime to allow a cheap
    # unchanged-file check without computing checksums.
    existing_index: dict[str, tuple[int, float]] = {}
    if (config.resume or config.resume_safe) and config.database.exists():
        with db.connect() as connection:
            initialise_database(connection)
            cursor = connection.execute(
                "SELECT path, size_bytes, mtime FROM " + LIBRARY_TABLE
            )
            for row in cursor.fetchall():
                existing_index[row["path"]] = (
                    row["size_bytes"],
                    row["mtime"],
                )

    # Estimate total files for progress reporting (may be I/O heavy for very
    # large libraries but provides a useful progress bar). If the user turns
    # off progress we avoid the full count.
    total_files = None
    if config.show_progress:
        total_files = sum(1 for _ in utils.iter_audio_files(config.root))

    with db.connect() as connection:
        initialise_database(connection)

        iterator = (
            Path(dirpath) / filename
            for dirpath, _, filenames in os.walk(config.root)
            for filename in filenames
            if utils.is_audio_file(filename)
        )
        # helper to yield batches while skipping unchanged files when resuming

        def batches() -> Iterator[list[Path]]:
            batch: list[Path] = []
            for path in iterator:
                npath = utils.normalise_path(str(path))
                try:
                    st = path.stat()
                except OSError:
                    # skip unreadable files
                    continue
                if config.resume_safe:
                    batch.append(path)
                    if len(batch) >= config.batch_size:
                        # If any file in batch is in existing_index with matching size and mtime, skip whole batch
                        skip_batch = False
                        for p in batch:
                            np = utils.normalise_path(str(p))
                            existing = existing_index.get(np)
                            if existing is not None:
                                size, mtime = existing
                                if size == p.stat().st_size and abs(mtime - p.stat().st_mtime) < 1.0:
                                    skip_batch = True
                                    break
                        if skip_batch:
                            batch = []
                            continue
                        yield batch
                        batch = []
                elif config.resume:
                    existing = existing_index.get(npath)
                    if existing is not None:
                        size, mtime = existing
                        # If size and mtime match (within a second) assume
                        # unchanged and skip recomputing expensive checksums.
                        if (
                            size == st.st_size
                            and abs(mtime - st.st_mtime) < 1.0
                        ):
                            # unchanged; skip
                            continue
                    batch.append(path)
                    if len(batch) >= config.batch_size:
                        yield batch
                        batch = []
                else:
                    batch.append(path)
                    if len(batch) >= config.batch_size:
                        yield batch
                        batch = []
            if batch:
                if config.resume_safe:
                    skip_batch = False
                    for p in batch:
                        np = utils.normalise_path(str(p))
                        existing = existing_index.get(np)
                        if existing is not None:
                            size, mtime = existing
                            if size == p.stat().st_size and abs(mtime - p.stat().st_mtime) < 1.0:
                                skip_batch = True
                                break
                    if not skip_batch:
                        yield batch
                else:
                    yield batch

        # iterate batches with optional progress bar
        if config.show_progress:
            try:
                from tqdm import tqdm  # type: ignore

                pbar = tqdm(total=total_files, unit="files")
            except Exception:  # pragma: no cover - fallback if tqdm missing
                class _DummyPbar:
                    def __init__(
                        self,
                        total: Optional[int] = None,
                        unit: Optional[str] = None,
                    ) -> None:
                        self.total = total

                    def update(self, n: int) -> None:
                        pass

                    def close(self) -> None:
                        pass

                pbar = _DummyPbar(total=total_files)
        else:
            pbar = None

        for batch in batches():
            records = list(_iter_records(batch, include_fingerprints))
            if not records:
                if pbar:
                    pbar.update(len(batch))
                continue
            _upsert_batch(connection, records)
            connection.commit()
            total += len(records)
            if pbar:
                pbar.update(len(batch))
            LOGGER.info(
                "Processed %s files (%.1fs elapsed)",
                total,
                time.time() - start,
            )

        if pbar:
            pbar.close()

    LOGGER.info("Completed scan of %s (%s files)", config.root, total)
    return total


def scan(
    root: Path,
    database: Path,
    include_fingerprints: bool = False,
    batch_size: int = 100,
    resume: bool = False,
    show_progress: bool = False,
    workers: int = 1,
) -> int:
    """Compatibility wrapper: simple API for scanning a library.

    Older or alternative callers (eg. codex refactor) may prefer a flat
    function signature instead of constructing a :class:`ScanConfig`. This
    convenience function builds a :class:`ScanConfig` and delegates to
    :func:`scan_library` so both APIs are supported.

    The current implementation ignores ``workers`` and runs single-threaded;
    the parameter is accepted for forward compatibility.
    """
    config = ScanConfig(
        root=root,
        database=database,
        include_fingerprints=include_fingerprints,
        batch_size=batch_size,
        resume=resume,
        show_progress=show_progress,
    )
    # NOTE: ``workers`` is currently unused; scanning remains single-process.
    return scan_library(config)
