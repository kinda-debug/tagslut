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

    Hash formula is implicit (no version column). Changing this function's
    payload construction will invalidate all previously recorded
    dj_validation_state.state_hash values, which is expected.

    Args:
        conn: Open SQLite connection to the v3 database.

    Returns:
        SHA256 hex digest of the sorted, concatenated identity IDs.
    """
    rows = conn.execute(
        """
        SELECT da.identity_id, ma.path, ma.status
        FROM dj_admission da
        JOIN mp3_asset ma ON ma.id = da.mp3_asset_id
        WHERE da.status = 'admitted'
        ORDER BY da.identity_id ASC
        """
    ).fetchall()

    if not rows:
        return hashlib.sha256(b"").hexdigest()

    # Sort by identity_id for determinism
    sorted_rows = sorted(rows, key=lambda r: int(r[0]))
    payload = ";".join(f"{r[0]}:{r[1]}:{r[2]}" for r in sorted_rows)
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
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(dj_validation_state)").fetchall()}
    if "validated_at" in columns:
        timestamp_column = "validated_at"
    elif "created_at" in columns:
        timestamp_column = "created_at"
    else:
        raise sqlite3.OperationalError(
            "dj_validation_state missing timestamp column (expected validated_at or created_at)"
        )

    conn.execute(
        f"""
        INSERT INTO dj_validation_state (state_hash, passed, issue_count, summary, {timestamp_column})
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            state_hash,
            int(passed),
            int(issue_count),
            summary or None,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
