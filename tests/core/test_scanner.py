from __future__ import annotations

import logging
from pathlib import Path

from tagslut.core.scanner import _log_scan_summary


def test_log_scan_summary_includes_core_counts(caplog) -> None:  # type: ignore[no-untyped-def]
    scanner_logger = logging.getLogger("tagslut.core.scanner")
    scanner_logger.addHandler(caplog.handler)
    caplog.set_level("INFO", logger="tagslut.core.scanner")
    try:
        _log_scan_summary(
            session_id=42,
            status="completed",
            discovered=1200,
            queued=250,
            skipped=950,
            succeeded=248,
            failed=2,
            duration=20.0,
            scan_integrity=True,
            scan_hash=False,
            library_name="COMMUNE",
            zone_name="auto",
            db_path=Path("/tmp/test.db"),
            skip_reasons={"up_to_date": 950},
        )
    finally:
        scanner_logger.removeHandler(caplog.handler)

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "SCAN COMPLETE" in text
    assert "Session: 42" in text
    assert "Discovered: 1,200" in text
    assert "Queued:     250" in text
    assert "Skipped:    950" in text
    assert "up_to_date: 950" in text


def test_log_scan_summary_logs_failure_breakdown_as_warning(caplog) -> None:  # type: ignore[no-untyped-def]
    scanner_logger = logging.getLogger("tagslut.core.scanner")
    scanner_logger.addHandler(caplog.handler)
    caplog.set_level("INFO", logger="tagslut.core.scanner")
    try:
        _log_scan_summary(
            session_id=7,
            status="completed",
            discovered=10,
            queued=10,
            skipped=0,
            succeeded=7,
            failed=3,
            duration=1.0,
            scan_integrity=False,
            scan_hash=False,
            library_name="COMMUNE",
            zone_name="auto",
            db_path=Path("/tmp/test.db"),
            failure_reasons={"InvalidFLAC": 2, "PermissionDenied": 1},
        )
    finally:
        scanner_logger.removeHandler(caplog.handler)

    warnings = [rec.getMessage() for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("InvalidFLAC: 2" in message for message in warnings)
    assert any("PermissionDenied: 1" in message for message in warnings)


def test_log_scan_summary_aborted_logs_resume_hint(caplog) -> None:  # type: ignore[no-untyped-def]
    scanner_logger = logging.getLogger("tagslut.core.scanner")
    scanner_logger.addHandler(caplog.handler)
    caplog.set_level("INFO", logger="tagslut.core.scanner")
    try:
        _log_scan_summary(
            session_id=9,
            status="aborted",
            discovered=100,
            queued=80,
            skipped=20,
            succeeded=40,
            failed=2,
            duration=4.0,
            scan_integrity=True,
            scan_hash=True,
            library_name="COMMUNE",
            zone_name="auto",
            db_path=Path("/tmp/test.db"),
        )
    finally:
        scanner_logger.removeHandler(caplog.handler)

    text = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "Partial results were committed in batches before interruption" in text
    assert "Re-run with --incremental to resume from where you left off" in text
