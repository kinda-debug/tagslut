"""Deduplication helpers for the library database."""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from . import scanner, utils

logger = logging.getLogger(__name__)


def _canonical_sort_key(row: sqlite3.Row) -> tuple:
    """Return a tuple used to rank potential canonical files."""

    return (
        row["fingerprint"] is not None,
        row["bit_rate"] or 0,
        row["sample_rate"] or 0,
        row["bit_depth"] or 0,
        row["duration"] or 0.0,
        -(row["size_bytes"] or 0),
    )


def deduplicate_database(db_path: Path, report_path: Optional[Path] = None) -> dict:
    """Identify duplicate files and mark canonical entries."""

    db_path = Path(utils.normalise_path(str(db_path)))
    db = utils.DatabaseContext(db_path)
    summary: dict[str, object] = {"groups": 0, "files": 0}
    report: List[dict[str, object]] = []

    with db.connect() as connection:
        scanner.initialise_database(connection)
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(
            """
            SELECT path, size_bytes, duration, sample_rate, bit_rate,
                   channels, bit_depth, checksum, fingerprint, fingerprint_duration,
                   tags_json
            FROM library_files
            WHERE checksum IS NOT NULL
            """
        )
        rows = cursor.fetchall()

    groups: dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        key = f"{row['checksum']}:{row['duration'] or 0}:{row['fingerprint'] or ''}"
        groups.setdefault(key, []).append(row)

    with db.connect() as connection:
        for key, members in groups.items():
            if len(members) < 2:
                continue
            summary["groups"] = summary.get("groups", 0) + 1
            sorted_members = sorted(members, key=_canonical_sort_key, reverse=True)
            for idx, member in enumerate(sorted_members, start=1):
                connection.execute(
                    """
                    UPDATE library_files
                    SET dup_group=?, duplicate_rank=?, is_canonical=?
                    WHERE path=?
                    """,
                    (
                        key,
                        idx,
                        1 if idx == 1 else 0,
                        utils.normalise_path(member["path"]),
                    ),
                )
                if idx > 1:
                    summary["files"] = summary.get("files", 0) + 1
            report.append(
                {
                    "group": key,
                    "canonical": sorted_members[0]["path"],
                    "duplicates": [m["path"] for m in sorted_members[1:]],
                }
            )
        connection.commit()

    if report_path is not None:
        utils.ensure_parent_directory(report_path)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf8"
        )

    summary["report"] = str(report_path) if report_path else None
    return summary
