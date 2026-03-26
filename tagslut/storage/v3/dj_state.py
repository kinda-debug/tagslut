"""DJ pipeline state hash computation (deterministic across runs).

This module provides utilities for computing stable fingerprints of the DJ
admission state so that patches/exports can detect changes without scanning
the entire pool on every run.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone


def compute_dj_state_hash(conn: sqlite3.Connection) -> str:
    """
    Compute a deterministic hash of the current DJ admission state.

    Fetches all admitted identity IDs from dj_admission table, sorts them,
    and returns their SHA256 fingerprint. The sort ensures that the hash is
    identical across runs, even if the database query returns rows in a
    different order.

    Args:
        conn: Open SQLite connection to the v3 database.

    Returns:
        SHA256 hex digest of the sorted, concatenated identity IDs.
    """
    rows = conn.execute(
        "SELECT identity_id FROM dj_admission WHERE status = 'admitted' ORDER BY identity_id ASC"
    ).fetchall()

    if not rows:
        return hashlib.sha256(b"").hexdigest()

    # Flatten and sort to ensure determinism
    identity_ids = sorted([int(row[0]) for row in rows])
    payload = ",".join(str(id) for id in identity_ids)
    return hashlib.sha256(payload.encode()).hexdigest()


def record_validation_state(
    conn: sqlite3.Connection,
    state_hash: str,
    issue_count: int,
    passed: bool,
    summary: str = "",
) -> None:
    """
    Record a DJ validation state row.

    Args:
        conn: SQLite connection
        state_hash: Hash computed by compute_dj_state_hash()
        issue_count: Number of issues found during validation
        passed: Whether validation passed
        summary: Optional text summary
    """
    conn.execute(
        """
        INSERT INTO dj_validation_state (state_hash, passed, created_at)
        VALUES (?, ?, ?)
        """,
        (state_hash, int(passed), datetime.now(timezone.utc).isoformat()),
    )
