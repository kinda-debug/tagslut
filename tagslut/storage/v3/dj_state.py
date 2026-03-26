"""DJ state hashing utilities.

The DJ pipeline uses a stable "state_hash" to gate XML emits behind a prior
passing `tagslut dj validate` run. This hash must be deterministic across
identical DB states.
"""

from __future__ import annotations

import hashlib
import sqlite3


def compute_dj_state_hash(conn: sqlite3.Connection) -> str:
    """Compute a deterministic hash for the current DJ DB state.

    Contract:
      - Run: `SELECT id FROM dj_admission ORDER BY id ASC`
      - SHA-256 the concatenated IDs (newline-delimited).
    """
    rows = conn.execute("SELECT id FROM dj_admission ORDER BY id ASC").fetchall()
    digest = hashlib.sha256()
    for (dj_admission_id,) in rows:
        digest.update(str(int(dj_admission_id)).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
