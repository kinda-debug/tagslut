from __future__ import annotations

import hashlib
import sqlite3


def compute_dj_state_hash(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT id FROM dj_admission ORDER BY id ASC").fetchall()
    payload = "".join(str(int(row[0])) for row in rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

