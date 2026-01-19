#!/usr/bin/env python3
"""
Scan database for files with suspicious durations.

Identifies:
1. Files longer than expected (stitched recoveries)
2. Files shorter than expected (truncated)
3. Files with MusicBrainz metadata but no duration validation

Usage:
    python tools/integrity/validate_durations.py --db path/to/music.db
    python tools/integrity/validate_durations.py --db path/to/music.db --strict
    python tools/integrity/validate_durations.py --db path/to/music.db --zone suspect
"""

import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional

import click

sys.path.insert(0, str(Path(__file__).parents[2]))

from dedupe.core.duration_validator import (
    check_file_duration,
    format_mismatch_report,
    DEFAULT_TOLERANCE_SECONDS,
    STRICT_TOLERANCE_SECONDS,
)
from dedupe.storage.schema import get_connection
from dedupe.utils.cli_helper import common_options, configure_execution
from dedupe.utils import env_paths

logger = logging.getLogger("dedupe")


def scan_database_durations(
    db_path: Path,
    zone: Optional[str] = None,
    tolerance: float = DEFAULT_TOLERANCE_SECONDS,
    output_json: Optional[Path] = None,
):
    """
    Scans database for files with duration mismatches.

    Args:
        db_path: Path to SQLite database
        zone: Only check files in specific zone (e.g., "suspect")
        tolerance: Allowed variance in seconds
        output_json: Optional path to write JSON report
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Build query
    query = """
        SELECT 
            path,
            duration,
            metadata_json,
            zone,
            library,
            flac_ok,
            integrity_state
        FROM files
        WHERE duration IS NOT NULL 
          AND duration > 0
          AND metadata_json IS NOT NULL
    """

    if zone:
        query += " AND zone = ?"
        cursor.execute(query, (zone,))
    else:
        cursor.execute(query)

    results = {
        "critical": [],
        "warning": [],
        "ok": [],
    }

    total_checked = 0
    total_with_expected = 0

    for row in cursor.fetchall():
        total_checked += 1
        path = Path(row[0])
        actual_duration = row[1]

        # Parse metadata
        try:
            tags = json.loads(row[2]) if row[2] else {}
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON metadata for {path}")
            continue

        # Check duration
        mismatch = check_file_duration(actual_duration, tags, tolerance)

        if mismatch is None:
            # No expected duration found in tags
            continue

        total_with_expected += 1
        mismatch.path = path

        # Categorize
        if mismatch.severity == "critical":
            results["critical"].append(mismatch)
            logger.error(format_mismatch_report(mismatch))
        elif mismatch.severity == "warning":
            results["warning"].append(mismatch)
            logger.warning(format_mismatch_report(mismatch))
        else:
            results["ok"].append(mismatch)
            logger.debug(format_mismatch_report(mismatch))

    # Summary
    logger.info("=" * 80)
    logger.info("DURATION VALIDATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total files checked: {total_checked}")
    logger.info(f"Files with expected duration: {total_with_expected}")
    logger.info(f"Critical issues: {len(results['critical'])}")
    logger.info(f"Warnings: {len(results['warning'])}")
    logger.info(f"OK: {len(results['ok'])}")

    # List critical files
    if results["critical"]:
        logger.info("\n🔴 CRITICAL FILES (likely stitched or truncated):")
        for m in results["critical"]:
            logger.info(f"  {m.path}")
            logger.info(f"    Actual: {m.actual_duration:.2f}s | Expected: {m.expected_duration:.2f}s | Diff: {m.difference:+.2f}s")

    # List warnings
    if results["warning"]:
        logger.info("\n🟡 WARNING FILES (minor duration mismatch):")
        for m in results["warning"]:
            logger.info(f"  {m.path}")
            logger.info(f"    Actual: {m.actual_duration:.2f}s | Expected: {m.expected_duration:.2f}s | Diff: {m.difference:+.2f}s")

    # Write JSON report
    if output_json:
        report = {
            "summary": {
                "total_checked": total_checked,
                "with_expected_duration": total_with_expected,
                "critical_count": len(results["critical"]),
                "warning_count": len(results["warning"]),
                "ok_count": len(results["ok"]),
                "tolerance_seconds": tolerance,
            },
            "critical_files": [
                {
                    "path": str(m.path),
                    "actual_duration": m.actual_duration,
                    "expected_duration": m.expected_duration,
                    "difference": m.difference,
                    "type": m.mismatch_type,
                    "likely_stitched": m.is_likely_stitched,
                }
                for m in results["critical"]
            ],
            "warning_files": [
                {
                    "path": str(m.path),
                    "actual_duration": m.actual_duration,
                    "expected_duration": m.expected_duration,
                    "difference": m.difference,
                    "type": m.mismatch_type,
                }
                for m in results["warning"]
            ],
        }

        with open(output_json, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"\n✓ JSON report written to: {output_json}")

    conn.close()
    return results


@click.command()
@click.option(
    "--db",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to SQLite database (default: from config/environment)",
)
@click.option(
    "--zone",
    type=str,
    help="Only check files in specific zone (e.g., suspect)",
)
@click.option(
    "--strict",
    is_flag=True,
    help=f"Use strict tolerance ({STRICT_TOLERANCE_SECONDS}s instead of {DEFAULT_TOLERANCE_SECONDS}s)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Write JSON report to file",
)
@common_options
def main(
    db: str,
    zone: Optional[str],
    strict: bool,
    output: Optional[str],
    verbose: bool,
    config: Optional[str],
):
    """
    Validate file durations against expected values from metadata.

    Identifies files that are:
    - Longer than expected (likely stitched R-Studio recoveries)
    - Shorter than expected (truncated or corrupt)
    - Missing expected duration metadata

    Examples:
        # Check all files
        python tools/integrity/validate_durations.py --db music.db

        # Check only suspect zone with strict tolerance
        python tools/integrity/validate_durations.py --db music.db --zone suspect --strict

        # Generate JSON report
        python tools/integrity/validate_durations.py --db music.db -o duration_report.json
    """
    configure_execution(verbose, config)
    
    # Get database path from config if not provided
    if not db:
        db = env_paths.get_db_path()
        if not db:
            logger.error("No database path found in config. Set DEDUPE_DB environment variable or use --db")
            raise click.ClickException("Database path not configured")
        logger.info(f"Using database from config: {db}")

    tolerance = STRICT_TOLERANCE_SECONDS if strict else DEFAULT_TOLERANCE_SECONDS
    output_path = Path(output) if output else None

    scan_database_durations(
        db_path=Path(db),
        zone=zone,
        tolerance=tolerance,
        output_json=output_path,
    )


if __name__ == "__main__":
    main()
