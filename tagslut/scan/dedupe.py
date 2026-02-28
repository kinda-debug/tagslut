"""
Canonical copy election. No deletion.
Election criteria (in order): quality_rank ASC, identity_confidence DESC, size_bytes DESC.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from tagslut.scan.constants import DEDUPE_ISRC_MIN_CONFIDENCE


@dataclass
class FileCandidate:
    path: Path
    checksum: str
    quality_rank: Optional[int]
    identity_confidence: int
    size_bytes: int


def elect_canonical(candidates: List[FileCandidate]) -> str:
    """Return the checksum of the elected canonical copy."""

    def sort_key(candidate: FileCandidate):
        rank = candidate.quality_rank if candidate.quality_rank is not None else 999
        return (rank, -candidate.identity_confidence, -candidate.size_bytes)

    return sorted(candidates, key=sort_key)[0].checksum


def find_exact_duplicates(conn: sqlite3.Connection, checksum: str) -> List[str]:
    """Return paths of all other files with the same checksum."""
    rows = conn.execute("SELECT path FROM files WHERE checksum = ?", (checksum,)).fetchall()
    return [row[0] for row in rows]


def mark_format_duplicates(conn: sqlite3.Connection) -> int:
    """
    For each group of files sharing a single canonical_isrc (with confidence >= threshold),
    elect a canonical and mark the rest as FORMAT_DUPLICATE.
    Returns count of files marked.
    """
    marked = 0
    rows = conn.execute(
        """
        SELECT canonical_isrc, COUNT(*) as cnt
        FROM files
        WHERE canonical_isrc IS NOT NULL
          AND identity_confidence >= ?
          AND COALESCE(scan_status, '') != 'CORRUPT'
        GROUP BY canonical_isrc
        HAVING cnt > 1
        """,
        (DEDUPE_ISRC_MIN_CONFIDENCE,),
    ).fetchall()

    for row in rows:
        isrc = row[0]
        group = conn.execute(
            """
            SELECT path, checksum, quality_rank, identity_confidence, size
            FROM files
            WHERE canonical_isrc = ? AND identity_confidence >= ?
            """,
            (isrc, DEDUPE_ISRC_MIN_CONFIDENCE),
        ).fetchall()

        candidates = [
            FileCandidate(
                path=Path(r[0]),
                checksum=r[1],
                quality_rank=r[2],
                identity_confidence=r[3],
                size_bytes=r[4] or 0,
            )
            for r in group
        ]
        canonical_checksum = elect_canonical(candidates)

        for candidate in candidates:
            if candidate.checksum != canonical_checksum:
                conn.execute(
                    """
                    UPDATE files
                    SET scan_status = 'FORMAT_DUPLICATE', duplicate_of_checksum = ?
                    WHERE checksum = ?
                    """,
                    (canonical_checksum, candidate.checksum),
                )
                marked += 1

    return marked
