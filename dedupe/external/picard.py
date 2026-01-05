"""Tagger reconciliation helpers (Yate-first workflow)."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from dedupe import metadata
from dedupe.healthcheck import evaluate_flac
from dedupe.storage import initialise_library_schema
from dedupe.storage.queries import (
    fetch_records_by_state,
    record_picard_move,
    update_library_path,
    upsert_library_rows,
)
from dedupe.utils import compute_md5, iter_audio_files, normalise_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PicardReconcileResult:
    """Summary of a tagger reconciliation run."""

    moved: int
    unchanged: int
    inserted: int


@dataclass(slots=True)
class StagingEntry:
    """In-memory representation of a staging record."""

    path: Path
    checksum: str | None
    size_bytes: int | None


def _build_staging_index(entries: Iterable[sqlite3.Row]) -> dict[tuple[str | None, int | None], list[StagingEntry]]:
    """Index staging entries by checksum and size for quick lookup."""

    index: dict[tuple[str | None, int | None], list[StagingEntry]] = {}
    for row in entries:
        checksum = row["checksum"]
        size = row["size_bytes"]
        entry = StagingEntry(
            path=Path(row["path"]),
            checksum=checksum,
            size_bytes=size,
        )
        index.setdefault((checksum, size), []).append(entry)
    return index


def _prepare_payload(path: Path, library_state: str) -> dict[str, object]:
    """Collect metadata for a path to insert into the library table."""

    meta = metadata.probe_audio(path)
    health = evaluate_flac(path)
    integrity_state = "valid" if health.audio_ok else "recoverable"
    return {
        "path": normalise_path(str(path)),
        "size_bytes": meta.size_bytes,
        "mtime": path.stat().st_mtime,
        "checksum": compute_md5(path),
        "duration": meta.stream.duration,
        "sample_rate": meta.stream.sample_rate,
        "bit_rate": meta.stream.bit_rate,
        "channels": meta.stream.channels,
        "bit_depth": meta.stream.bit_depth,
        "tags_json": json.dumps(meta.tags, sort_keys=True, separators=(",", ":")),
        "fingerprint": None,
        "fingerprint_duration": None,
        "dup_group": None,
        "duplicate_rank": None,
        "is_canonical": None,
        "extra_json": json.dumps(
            {
                "health_score": health.score,
                "health_reasons": health.reasons,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "library_state": library_state,
        "flac_ok": 1 if health.audio_ok else 0,
        "integrity_state": integrity_state,
        "zone": "staging" if library_state == "staging" else None,
    }


def reconcile_picard_changes(
    connection: sqlite3.Connection,
    staging_root: Path,
    *,
    strict: bool = True,
) -> PicardReconcileResult:
    """Detect tagger moves in *staging_root* and reconcile the database."""

    initialise_library_schema(connection)
    staging_root = Path(normalise_path(str(staging_root)))
    if not staging_root.is_dir():
        raise FileNotFoundError(f"Staging root not found: {staging_root}")

    existing = fetch_records_by_state(connection, "staging")
    index = _build_staging_index(existing)
    seen_paths: set[str] = set()
    moved = 0
    unchanged = 0
    inserted = 0

    for path in iter_audio_files(staging_root):
        checksum = compute_md5(path)
        size = path.stat().st_size
        key = (checksum, size)
        matches = index.get(key, [])
        normalised = normalise_path(str(path))
        if matches:
            match = matches.pop(0)
            seen_paths.add(normalise_path(str(match.path)))
            if normalised != normalise_path(str(match.path)):
                update_library_path(connection, match.path, path, library_state="staging")
                record_picard_move(connection, match.path, path, checksum)
                moved += 1
            else:
                unchanged += 1
            continue

        payload = _prepare_payload(path, "staging")
        upsert_library_rows(connection, [payload])
        inserted += 1

    missing = [
        row["path"]
        for row in existing
        if normalise_path(row["path"]) not in seen_paths
    ]
    if missing and strict:
        logger.error("Missing staging files after tagger reconciliation: %s", missing)
        raise RuntimeError(
            "Tagger reconciliation detected missing staging files; "
            "run with strict=False or rescan staging."
        )
    if missing:
        logger.warning("Missing staging files after tagger reconciliation: %s", missing)

    return PicardReconcileResult(moved=moved, unchanged=unchanged, inserted=inserted)
