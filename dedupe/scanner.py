"""Library scanner that records audio metadata into SQLite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import fingerprints, metadata, utils
from .db import LIBRARY_TABLE, initialise_library_schema


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ScanRecord:
    """Metadata record for a scanned audio file."""

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
    dup_group: Optional[str]
    duplicate_rank: Optional[int]
    is_canonical: Optional[int]
    extra_json: Optional[str]


@dataclass(slots=True)
class ScanConfig:
    """Configuration for :func:`scan_library`.

    Attributes:
        root: root path to scan
        database: sqlite database path
        include_fingerprints: whether to request Chromaprint fingerprints
        batch_size: number of files per DB upsert
        resume: skip files already indexed and unchanged
        resume_safe: skip a batch if any member matches an unchanged file
        show_progress: display a progress bar during scanning
    """

    root: Path
    database: Path
    include_fingerprints: bool = False
    batch_size: int = 100
    resume: bool = False
    resume_safe: bool = False
    show_progress: bool = False


def initialise_database(connection: sqlite3.Connection) -> None:
    """Ensure the SQLite schema exists."""

    initialise_library_schema(connection)


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
        logger.info(
            "Chromaprint fingerprints requested but fpcalc not available; "
            "continuing without fingerprints",
        )
        return False
    logger.info("Chromaprint fingerprints enabled for this scan")
    return True


def prepare_record(path: Path, include_fingerprints: bool) -> ScanRecord:
    """Collect metadata and optional fingerprint information for *path*."""
    meta = metadata.probe_audio(path)
    checksum = utils.compute_md5(path)
    fingerprint_result = (
        fingerprints.generate_chromaprint(path) if include_fingerprints else None
    )
    return ScanRecord(
        path=utils.normalise_path(str(path)),
        size_bytes=meta.size_bytes,
        mtime=path.stat().st_mtime,
        checksum=checksum,
        duration=meta.stream.duration,
        sample_rate=meta.stream.sample_rate,
        bit_rate=meta.stream.bit_rate,
        channels=meta.stream.channels,
        bit_depth=meta.stream.bit_depth,
        tags_json=json.dumps(meta.tags, sort_keys=True, separators=(",", ":")),
        fingerprint=(fingerprint_result.fingerprint if fingerprint_result else None),
        fingerprint_duration=(
            fingerprint_result.duration if fingerprint_result else None
        ),
        dup_group=None,
        duplicate_rank=None,
        is_canonical=None,
        extra_json=None,
    )


def _iter_records(
    paths: Iterable[Path],
    include_fingerprints: bool,
) -> Iterator[ScanRecord]:
    """Yield :class:`ScanRecord` objects for each path, logging failures."""
    for path in paths:
        try:
            yield prepare_record(path, include_fingerprints)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to scan %s: %s", path, exc)


def _upsert_batch(
    connection: sqlite3.Connection,
    records: Iterable[ScanRecord],
) -> None:
    """Insert or update a batch of records in the library table."""
    payload: list[dict[str, object]] = []
    for record in records:
        row = asdict(record)
        row["path"] = utils.normalise_path(row["path"])
        payload.append(row)

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
            fingerprint_duration,
            dup_group,
            duplicate_rank,
            is_canonical,
            extra_json
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
            :fingerprint_duration,
            :dup_group,
            :duplicate_rank,
            :is_canonical,
            :extra_json
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
            fingerprint_duration=excluded.fingerprint_duration,
            dup_group=excluded.dup_group,
            duplicate_rank=excluded.duplicate_rank,
            is_canonical=excluded.is_canonical,
            extra_json=excluded.extra_json
        """,
        payload,
    )


def scan_library(config: ScanConfig) -> int:
    """Scan ``config.root`` recursively and populate ``config.database``."""
    root = Path(utils.normalise_path(str(config.root)))
    database = Path(utils.normalise_path(str(config.database)))

    utils.ensure_parent_directory(database)
    db = utils.DatabaseContext(database)
    start = time.time()
    total = 0
    include_fingerprints = resolve_fingerprint_usage(config.include_fingerprints)

    # Build an index of already-scanned files when resuming. We index by the
    # normalised path and record the size and mtime to allow a cheap
    # unchanged-file check without computing checksums.
    existing_index: dict[str, tuple[int, float]] = {}
    if (config.resume or config.resume_safe) and database.exists():
        with db.connect() as connection:
            initialise_database(connection)
            cursor = connection.execute(
                "SELECT path, size_bytes, mtime FROM " + LIBRARY_TABLE
            )
            for row in cursor.fetchall():
                normalised_path = utils.normalise_path(row["path"])
                existing_index[normalised_path] = (
                    row["size_bytes"],
                    row["mtime"],
                )

    # Estimate total files for progress reporting (may be I/O heavy for very
    # large libraries but provides a useful progress bar). If the user turns
    # off progress we avoid the full count.
    total_files: Optional[int] = None
    if config.show_progress:
        total_files = sum(1 for _ in utils.iter_audio_files(root))

    with db.connect() as connection:
        initialise_database(connection)

        iterator = (
            Path(dirpath) / filename
            for dirpath, _, filenames in os.walk(root)
            for filename in filenames
            if utils.is_audio_file(filename)
        )
        # Helper to yield batches while skipping unchanged files when resuming.

        def batches() -> Iterator[list[tuple[Path, bool]]]:
            batch: list[tuple[Path, bool]] = []
            for path in iterator:
                normalised_path = utils.normalise_path(str(path))
                try:
                    st = path.stat()
                except OSError:
                    # skip unreadable files
                    continue
                unchanged = False
                if config.resume or config.resume_safe:
                    existing = existing_index.get(normalised_path)
                    if existing is not None:
                        size, mtime = existing
                        unchanged = (
                            size == st.st_size and abs(mtime - st.st_mtime) < 1.0
                        )
                batch.append((path, unchanged))
                if len(batch) >= config.batch_size:
                    yield batch
                    batch = []
            if batch:
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
            if config.resume_safe and any(item[1] for item in batch):
                if pbar:
                    pbar.update(len(batch))
                continue

            paths = [
                path for path, unchanged in batch if not (config.resume and unchanged)
            ]
            if pbar:
                pbar.update(len(batch))

            if not paths:
                continue

            records = list(_iter_records(paths, include_fingerprints))
            if not records:
                continue
            _upsert_batch(connection, records)
            connection.commit()
            total += len(records)
            logger.info(
                "Processed %s files (%.1fs elapsed)",
                total,
                time.time() - start,
            )

        if pbar:
            pbar.close()

    logger.info("Completed scan of %s (%s files)", root, total)
    return total


def scan(
    root: Path,
    database: Path,
    include_fingerprints: bool = False,
    batch_size: int = 100,
    resume: bool = False,
    resume_safe: bool = False,
    show_progress: bool = False,
) -> int:
    """Compatibility wrapper providing a flat API for scanning a library.

    Older or alternative callers (eg. codex refactor) may prefer a flat
    function signature instead of constructing a :class:`ScanConfig`. This
    convenience function builds a :class:`ScanConfig` and delegates to
    :func:`scan_library` so both APIs are supported.
    """
    config = ScanConfig(
        root=root,
        database=database,
        include_fingerprints=include_fingerprints,
        batch_size=batch_size,
        resume=resume,
        resume_safe=resume_safe,
        show_progress=show_progress,
    )
    return scan_library(config)


def rescan_missing(
    root: Path,
    database: Path,
    include_fingerprints: bool = False,
) -> dict[str, list[str]]:
    """Ingest only FLAC files that are absent from the existing database."""

    root = Path(utils.normalise_path(str(root)))
    database = Path(utils.normalise_path(str(database)))
    utils.ensure_parent_directory(database)
    db = utils.DatabaseContext(database)
    missing: list[str] = []
    ingested: list[str] = []
    unreadable: list[str] = []
    corrupt: list[str] = []

    with db.connect() as connection:
        initialise_database(connection)
        connection.row_factory = sqlite3.Row
        existing = {
            utils.normalise_path(row["path"])
            for row in connection.execute(
                "SELECT path FROM " + LIBRARY_TABLE
            ).fetchall()
        }

    def _iter_flac() -> Iterator[Path]:
        for path in root.rglob("*.flac"):
            yield path

    targets: list[Path] = []
    for path in _iter_flac():
        normalised_path = utils.normalise_path(str(path))
        if normalised_path in existing:
            continue
        missing.append(normalised_path)
        targets.append(path)

    include = resolve_fingerprint_usage(include_fingerprints)
    records: list[ScanRecord] = []
    for path in targets:
        try:
            records.append(prepare_record(path, include))
        except FileNotFoundError:
            unreadable.append(utils.normalise_path(str(path)))
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to ingest %s", path)
            corrupt.append(utils.normalise_path(str(path)))

    with db.connect() as connection:
        if records:
            _upsert_batch(connection, records)
            connection.commit()
            ingested = [r.path for r in records]

    return {
        "missing": missing,
        "ingested": ingested,
        "unreadable": unreadable,
        "corrupt": corrupt,
    }
