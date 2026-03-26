"""DJ validate helpers (DJ pipeline Stage 3b).

Stage 3 validation is implemented in `tagslut.dj.admission.validate_dj_library()`.
This module provides a stable import path for tooling and type-checking.
"""

from __future__ import annotations

import sqlite3

from tagslut.dj.admission import record_validation_state, validate_dj_library
from tagslut.storage.v3.dj_state import compute_dj_state_hash


def validate_and_record_dj_state(
    conn: sqlite3.Connection,
) -> tuple[object, str | None, str | None]:
    """Validate the DJ library and attempt to record a dj_validation_state row.

    Returns: (report, state_hash|None, warning|None)
    """
    report = validate_dj_library(conn)
    state_hash = compute_dj_state_hash(conn)
    try:
        record_validation_state(
            conn,
            state_hash=state_hash,
            issue_count=len(getattr(report, "issues", [])),
            passed=bool(getattr(report, "ok", False)),
            summary=str(getattr(report, "summary", lambda: "")()),
        )
        conn.commit()
        return report, state_hash, None
    except sqlite3.OperationalError as exc:
        return report, state_hash, f"WARNING: dj validation state was not recorded; {exc}"

