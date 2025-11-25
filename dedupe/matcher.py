"""Matching logic between scanned libraries and recovery candidates."""

from __future__ import annotations

import csv
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from difflib import SequenceMatcher

from . import scanner, utils

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LibraryEntry:
    """Row captured by :mod:`dedupe.scanner`."""

    path: str
    name: str
    size_bytes: int
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    fingerprint: Optional[str]


@dataclass(slots=True)
class RecoveryEntry:
    """Row parsed from recovered metadata exports."""

    source_path: str
    suggested_name: str
    size_bytes: Optional[int]
    extension: Optional[str]

    @property
    def name(self) -> str:
        return self.suggested_name or Path(self.source_path).name


@dataclass(slots=True)
class MatchCandidate:
    """Outcome of matching a library entry to a recovery candidate."""

    library_path: str
    recovery_path: Optional[str]
    recovery_name: Optional[str]
    score: float
    classification: str
    filename_similarity: float
    size_difference: Optional[int]
    fingerprint_similarity: Optional[float]


def _row_to_library_entry(row: sqlite3.Row) -> LibraryEntry:
    """Convert a SQLite row into a :class:`LibraryEntry`."""
    return LibraryEntry(
        path=utils.normalise_path(row["path"]),
        name=Path(utils.normalise_path(row["path"])).name,
        size_bytes=row["size_bytes"],
        duration=row["duration"],
        sample_rate=row["sample_rate"],
        bit_rate=row["bit_rate"],
        fingerprint=row["fingerprint"],
    )


def _row_to_recovery_entry(row: sqlite3.Row) -> RecoveryEntry:
    """Convert a SQLite row into a :class:`RecoveryEntry`."""
    return RecoveryEntry(
        source_path=utils.normalise_path(row["source_path"]),
        suggested_name=row["suggested_name"],
        size_bytes=row["size_bytes"],
        extension=row["extension"],
    )


def load_library_entries(database: Path) -> list[LibraryEntry]:
    """Load scanned library entries from ``database``."""
    db = utils.DatabaseContext(Path(utils.normalise_path(str(database))))
    with db.connect() as connection:
        cursor = connection.execute(f"SELECT * FROM {scanner.LIBRARY_TABLE}")
        entries = [_row_to_library_entry(row) for row in cursor.fetchall()]
    logger.info("Loaded %s library entries", len(entries))
    return entries


def load_recovery_entries(database: Path) -> list[RecoveryEntry]:
    """Load recovery entries from the exported metadata database."""
    db = utils.DatabaseContext(Path(utils.normalise_path(str(database))))
    with db.connect() as connection:
        cursor = connection.execute("SELECT * FROM recovered_files")
        entries = [_row_to_recovery_entry(row) for row in cursor.fetchall()]
    logger.info("Loaded %s recovery entries", len(entries))
    return entries


def _filename_similarity(a: str, b: str) -> float:
    """Return a similarity ratio between two filenames (case-insensitive)."""

    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _size_difference(lib: LibraryEntry, recovery: RecoveryEntry) -> Optional[int]:
    """Return size delta between library and recovery entries when available."""

    if recovery.size_bytes is None:
        return None
    return recovery.size_bytes - lib.size_bytes


def _quality_classification(
    lib: LibraryEntry,
    recovery: Optional[RecoveryEntry],
    score: float,
    size_delta: Optional[int],
) -> str:
    """Classify a match based on similarity and size information."""

    if recovery is None:
        return "missing"
    if score >= 0.9:
        return "exact"
    if size_delta is not None:
        if size_delta < 0:
            return "truncated"
        if size_delta > 0:
            return "potential_upgrade"
    return "ambiguous"


def _compute_score(
    lib: LibraryEntry,
    recovery: RecoveryEntry,
) -> tuple[float, float, Optional[int]]:
    """Compute combined match score and supporting metrics for two entries."""

    name_score = _filename_similarity(lib.name, recovery.name)
    size_delta = _size_difference(lib, recovery)
    if size_delta is None:
        size_score = 0.5
    else:
        ratio = 1 - min(abs(size_delta) / max(lib.size_bytes, 1), 1)
        size_score = max(ratio, 0.0)
    score = (name_score * 0.6) + (size_score * 0.4)
    return score, name_score, size_delta


def match_databases(
    library_db: Path,
    recovered_db: Path,
    output_csv: Path,
) -> list[MatchCandidate]:
    """Match scanned library entries with recovered candidates and write a CSV."""

    library_entries: list[LibraryEntry] = load_library_entries(library_db)
    recovery_entries: list[RecoveryEntry] = load_recovery_entries(recovered_db)
    used_recoveries: set[str] = set()
    matches: list[MatchCandidate] = []

    for lib in library_entries:
        best_candidate: Optional[MatchCandidate] = None
        for recovery in recovery_entries:
            score, name_score, size_delta = _compute_score(lib, recovery)
            if score < 0.35:
                continue
            classification = _quality_classification(
                lib,
                recovery,
                score,
                size_delta,
            )
            candidate = MatchCandidate(
                library_path=lib.path,
                recovery_path=recovery.source_path,
                recovery_name=recovery.name,
                score=score,
                classification=classification,
                filename_similarity=name_score,
                size_difference=size_delta,
                fingerprint_similarity=None,
            )
            if best_candidate is None or candidate.score > best_candidate.score:
                best_candidate = candidate
        if best_candidate is not None:
            matches.append(best_candidate)
            if best_candidate.recovery_path:
                used_recoveries.add(utils.normalise_path(best_candidate.recovery_path))
        else:
            matches.append(
                MatchCandidate(
                    library_path=lib.path,
                    recovery_path=None,
                    recovery_name=None,
                    score=0.0,
                    classification="missing",
                    filename_similarity=0.0,
                    size_difference=None,
                    fingerprint_similarity=None,
                )
            )

    for recovery in recovery_entries:
        normalised_source = utils.normalise_path(recovery.source_path)
        if normalised_source in used_recoveries:
            continue
        matches.append(
            MatchCandidate(
                library_path="",
                recovery_path=normalised_source,
                recovery_name=recovery.name,
                score=0.0,
                classification="orphan",
                filename_similarity=0.0,
                size_difference=None,
                fingerprint_similarity=None,
            )
        )

    utils.ensure_parent_directory(output_csv)
    with output_csv.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "library_path",
                "recovery_path",
                "recovery_name",
                "score",
                "classification",
                "filename_similarity",
                "size_difference",
                "fingerprint_similarity",
            ],
        )
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "library_path": match.library_path,
                    "recovery_path": match.recovery_path or "",
                    "recovery_name": match.recovery_name or "",
                    "score": f"{match.score:.3f}",
                    "classification": match.classification,
                    "filename_similarity": f"{match.filename_similarity:.3f}",
                    "size_difference": (
                        match.size_difference
                        if match.size_difference is not None
                        else ""
                    ),
                    "fingerprint_similarity": (
                        ""
                        if match.fingerprint_similarity is None
                        else f"{match.fingerprint_similarity:.3f}"
                    ),
                }
            )
    logger.info("Wrote %s matches to %s", len(matches), output_csv)
    return matches
