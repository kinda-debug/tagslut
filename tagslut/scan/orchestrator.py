"""Scanner orchestrator: scan_file + run_scan."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from tagslut.scan.classify import classify_primary_status, compute_identity_confidence
from tagslut.scan.discovery import discover_paths
from tagslut.scan.issues import IssueCodes, Severity, record_issue
from tagslut.scan.tags import (
    compute_quality_rank_from_technical,
    compute_sha256,
    extract_isrc_from_tags,
    read_raw_tags,
    read_technical,
)
from tagslut.scan.validate import decode_probe_edges, probe_duration_ffprobe

ReadTagsFn = Callable[[Path], tuple[dict[str, list[str]], dict[str, Any], list[str], Optional[int], Optional[float]]]
ChecksumFn = Callable[[Path], str]
ProbeDurationFn = Callable[[Path], Optional[float]]
DecodeProbeFn = Callable[[Path, Optional[float]], list[str]]
RecordIssueFn = Callable[[sqlite3.Connection, int, Path, str, str, dict, Optional[str]], None]


def _default_read_tags(
    path: Path,
) -> tuple[dict[str, list[str]], dict[str, Any], list[str], Optional[int], Optional[float]]:
    raw_tags = read_raw_tags(path)
    technical = read_technical(path)
    isrc_candidates = extract_isrc_from_tags(raw_tags)
    quality_rank = compute_quality_rank_from_technical(technical)
    duration_tagged = technical.get("duration_tagged")
    return raw_tags, technical, isrc_candidates, quality_rank, duration_tagged


def _upsert_file_row(
    conn: sqlite3.Connection,
    *,
    path: Path,
    checksum: str,
    scan_status: str,
    flags: list[str],
    actual_duration: Optional[float],
    duration_delta: Optional[float],
    identity_confidence: int,
    isrc_candidates: list[str],
    quality_rank: Optional[int],
    canonical_isrc: Optional[str],
) -> None:
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """
        UPDATE files SET
            checksum = COALESCE(?, checksum),
            scan_status = ?,
            scan_flags_json = ?,
            actual_duration = ?,
            duration_delta = ?,
            identity_confidence = ?,
            isrc_candidates_json = ?,
            last_scanned_at = ?,
            scan_stage_reached = 2,
            quality_rank = ?,
            canonical_isrc = ?
        WHERE path = ?
        """,
        (
            checksum,
            scan_status,
            json.dumps(flags),
            actual_duration,
            duration_delta,
            identity_confidence,
            json.dumps(isrc_candidates),
            now,
            quality_rank,
            canonical_isrc,
            str(path),
        ),
    )
    if cursor.rowcount == 0:
        conn.execute(
            """
            INSERT INTO files (
                path, checksum, metadata_json, scan_status, scan_flags_json,
                actual_duration, duration_delta, identity_confidence, isrc_candidates_json,
                last_scanned_at, scan_stage_reached, quality_rank, canonical_isrc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(path),
                checksum,
                "{}",
                scan_status,
                json.dumps(flags),
                actual_duration,
                duration_delta,
                identity_confidence,
                json.dumps(isrc_candidates),
                now,
                2,
                quality_rank,
                canonical_isrc,
            ),
        )


def scan_file(
    conn: sqlite3.Connection,
    run_id: int,
    path: Path,
    *,
    read_tags: ReadTagsFn = _default_read_tags,
    compute_checksum: ChecksumFn = compute_sha256,
    probe_duration: ProbeDurationFn = probe_duration_ffprobe,
    decode_probe: DecodeProbeFn = decode_probe_edges,
    record_issue_fn: RecordIssueFn = record_issue,
) -> dict[str, Any]:
    """Scan a single file and persist issues + files row in one transaction."""
    checksum = compute_checksum(path)

    try:
        raw_tags, technical, isrc_candidates, quality_rank, duration_tagged = read_tags(path)
        has_tags_error = False
    except Exception as exc:
        with conn:
            record_issue_fn(
                conn,
                run_id,
                path,
                IssueCodes.TAGS_UNREADABLE,
                Severity.ERROR,
                {"error": str(exc)},
                checksum,
            )
            _upsert_file_row(
                conn,
                path=path,
                checksum=checksum,
                scan_status="CORRUPT",
                flags=[],
                actual_duration=None,
                duration_delta=None,
                identity_confidence=0,
                isrc_candidates=[],
                quality_rank=None,
                canonical_isrc=None,
            )
        return {"path": str(path), "status": "CORRUPT", "checksum": checksum}

    actual_duration = probe_duration(path)
    decode_errors = decode_probe(path, actual_duration)

    duration_delta: Optional[float] = None
    if actual_duration is not None and duration_tagged is not None:
        duration_delta = actual_duration - duration_tagged

    confidence = compute_identity_confidence(raw_tags, isrc_candidates, duration_delta)
    scan_status, flags = classify_primary_status(has_tags_error, decode_errors, duration_delta)
    canonical_isrc = isrc_candidates[0] if len(isrc_candidates) == 1 else None

    with conn:
        if actual_duration is None:
            record_issue_fn(
                conn,
                run_id,
                path,
                IssueCodes.DURATION_UNVERIFIED,
                Severity.INFO,
                {"reason": "ffprobe not available"},
                checksum,
            )
        if not isrc_candidates:
            record_issue_fn(
                conn,
                run_id,
                path,
                IssueCodes.ISRC_MISSING,
                Severity.INFO,
                {"isrc_candidates": []},
                checksum,
            )
        elif len(isrc_candidates) > 1:
            record_issue_fn(
                conn,
                run_id,
                path,
                IssueCodes.MULTI_ISRC,
                Severity.INFO,
                {"isrc_candidates": isrc_candidates},
                checksum,
            )
        if decode_errors:
            record_issue_fn(
                conn,
                run_id,
                path,
                IssueCodes.CORRUPT_DECODE,
                Severity.ERROR,
                {"errors": decode_errors[:5]},
                checksum,
            )

        _upsert_file_row(
            conn,
            path=path,
            checksum=checksum,
            scan_status=scan_status,
            flags=flags,
            actual_duration=actual_duration,
            duration_delta=duration_delta,
            identity_confidence=confidence,
            isrc_candidates=isrc_candidates,
            quality_rank=quality_rank,
            canonical_isrc=canonical_isrc,
        )

    return {"path": str(path), "status": scan_status, "checksum": checksum}


def run_scan(
    conn: sqlite3.Connection,
    library_root: Path,
    *,
    discover: Callable[[Path], list[Path]] = discover_paths,
    scan_file_fn: Callable[..., dict[str, Any]] = scan_file,
) -> int:
    """
    Open a scan run, process queue items, and close it as COMPLETE/FAILED.
    Continues on per-file scan errors by recording SCAN_ERROR issues.
    """
    now = datetime.now().isoformat()
    with conn:
        conn.execute(
            """
            INSERT INTO scan_runs (library_root, mode, created_at, tool_versions_json)
            VALUES (?, 'initial', ?, ?)
            """,
            (str(library_root), now, json.dumps({"status": "RUNNING"})),
        )
        run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    paths = discover(library_root)
    with conn:
        for path in paths:
            existing = conn.execute(
                "SELECT id FROM scan_queue WHERE run_id = ? AND path = ?",
                (run_id, str(path)),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO scan_queue (run_id, path, size_bytes, mtime_ns, stage, state)
                    VALUES (?, ?, ?, ?, 0, 'PENDING')
                    """,
                    (run_id, str(path), None, None),
                )

    had_failures = False
    pending = conn.execute(
        "SELECT id, path FROM scan_queue WHERE run_id = ? AND state = 'PENDING' ORDER BY id",
        (run_id,),
    ).fetchall()

    for queue_id, path_str in pending:
        path = Path(path_str)
        with conn:
            conn.execute("UPDATE scan_queue SET state = 'RUNNING' WHERE id = ?", (queue_id,))
        try:
            scan_file_fn(conn, run_id, path)
            with conn:
                conn.execute("UPDATE scan_queue SET state = 'DONE', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), queue_id))
        except Exception as exc:
            had_failures = True
            with conn:
                record_issue(
                    conn,
                    run_id,
                    path,
                    "SCAN_ERROR",
                    Severity.ERROR,
                    {"error": str(exc)},
                    None,
                )
                conn.execute(
                    "UPDATE scan_queue SET state = 'FAILED', last_error = ?, updated_at = ? WHERE id = ?",
                    (str(exc), datetime.now().isoformat(), queue_id),
                )

    final_status = "FAILED" if had_failures else "COMPLETE"
    with conn:
        conn.execute(
            "UPDATE scan_runs SET completed_at = ?, tool_versions_json = ? WHERE id = ?",
            (datetime.now().isoformat(), json.dumps({"status": final_status}), run_id),
        )

    return int(run_id)
