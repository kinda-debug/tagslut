"""Append-only metadata archive writer."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def upsert_archive(
    conn: sqlite3.Connection,
    *,
    checksum: str,
    path: Path,
    raw_tags: Dict,
    technical: Dict,
    durations: Dict,
    isrc_candidates: List[str],
    identity_confidence: int,
    quality_rank: Optional[int],
) -> None:
    """
    Insert into file_metadata_archive if checksum is new (append-only).
    Always upsert file_path_history.
    """
    now = datetime.now().isoformat()

    existing = conn.execute(
        "SELECT checksum FROM file_metadata_archive WHERE checksum = ?",
        (checksum,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """
            INSERT INTO file_metadata_archive (
                checksum, first_seen_at, first_seen_path,
                raw_tags_json, technical_json, durations_json,
                isrc_candidates_json, identity_confidence, quality_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checksum,
                now,
                str(path),
                json.dumps(raw_tags),
                json.dumps(technical),
                json.dumps(durations),
                json.dumps(isrc_candidates),
                identity_confidence,
                quality_rank,
            ),
        )

    history = conn.execute(
        "SELECT id FROM file_path_history WHERE checksum = ? AND path = ?",
        (checksum, str(path)),
    ).fetchone()

    if history is None:
        conn.execute(
            "INSERT INTO file_path_history (checksum, path, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (checksum, str(path), now, now),
        )
    else:
        conn.execute(
            "UPDATE file_path_history SET last_seen_at = ? WHERE checksum = ? AND path = ?",
            (now, checksum, str(path)),
        )
