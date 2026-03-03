"""Issue codes, severities, and DB writer."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


class IssueCodes:
    TAGS_UNREADABLE = "TAGS_UNREADABLE"
    CORRUPT_DECODE = "CORRUPT_DECODE"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    MULTI_ISRC = "MULTI_ISRC"
    ISRC_MISSING = "ISRC_MISSING"
    DURATION_UNVERIFIED = "DURATION_UNVERIFIED"
    DECODE_UNVERIFIED = "DECODE_UNVERIFIED"


class Severity:
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


def record_issue(
    conn: sqlite3.Connection,
    run_id: int,
    path: Path,
    code: str,
    severity: str,
    evidence: dict,  # type: ignore  # TODO: mypy-strict
    checksum: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO scan_issues (run_id, path, checksum, issue_code, severity, evidence_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, str(path), checksum, code, severity, json.dumps(evidence), datetime.now().isoformat()),
    )
