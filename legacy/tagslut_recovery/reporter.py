"""
Recovery Reporter Module

Generates outcome reports for the recovery pipeline:
- Summary statistics
- Detailed CSV/JSON exports
- Outcome classification: valid / salvaged / unrecoverable
"""

import csv
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("tagslut.recovery")


class Reporter:
    """
    Generates recovery pipeline reports.

    Outcome Classes:
    - VALID: Passed initial flac -t (no repair needed)
    - SALVAGED: Failed initial, successfully repaired
    - UNRECOVERABLE: Repair failed or verification failed
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def summary(self) -> dict:  # type: ignore  # TODO: mypy-strict
        """
        Generate summary statistics.

        Returns:
            Dict with outcome counts and percentages
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    CASE
                        WHEN integrity_state = 'valid' AND recovery_status IS NULL
                            THEN 'valid'
                        WHEN recovery_status IN ('salvaged', 'already_valid')
                            THEN 'salvaged'
                        WHEN recovery_status IN ('failed', 'verify_failed')
                            THEN 'unrecoverable'
                        WHEN recovery_status = 'queued'
                            THEN 'pending_repair'
                        ELSE 'unknown'
                    END as outcome,
                    COUNT(*) as count
                FROM files
                WHERE integrity_state IS NOT NULL
                GROUP BY outcome
                """
            )

            results = {
                "valid": 0,
                "salvaged": 0,
                "unrecoverable": 0,
                "pending_repair": 0,
                "unknown": 0,
            }

            for row in cursor:
                outcome, count = row
                results[outcome] = count

            total = sum(results.values())
            results["total"] = total

            # Calculate percentages
            if total > 0:
                results["valid_pct"] = round(100 * results["valid"] / total, 1)  # type: ignore  # TODO: mypy-strict
                results["salvaged_pct"] = round(  # type: ignore  # TODO: mypy-strict
                    100 * results["salvaged"] / total, 1
                )
                results["unrecoverable_pct"] = round(  # type: ignore  # TODO: mypy-strict
                    100 * results["unrecoverable"] / total, 1
                )

            return results

        finally:
            conn.close()

    def export_csv(self, output_path: Path, include_valid: bool = False) -> int:
        """
        Export detailed results to CSV.

        Args:
            output_path: Path for CSV output
            include_valid: Include files that passed initial validation

        Returns:
            Number of rows written
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            where_clause = ""
            if not include_valid:
                where_clause = """
                WHERE integrity_state != 'valid'
                   OR recovery_status IS NOT NULL
                """

            cursor = conn.execute(
                f"""
                SELECT
                    path,
                    integrity_state,
                    recovery_status,
                    recovery_method,
                    duration,
                    new_duration,
                    duration_delta,
                    pcm_md5,
                    silence_events,
                    backup_path,
                    integrity_checked_at,
                    recovered_at,
                    verified_at,
                    CASE
                        WHEN integrity_state = 'valid' AND recovery_status IS NULL
                            THEN 'valid'
                        WHEN recovery_status IN ('salvaged', 'already_valid')
                            THEN 'salvaged'
                        WHEN recovery_status IN ('failed', 'verify_failed')
                            THEN 'unrecoverable'
                        WHEN recovery_status = 'queued'
                            THEN 'pending_repair'
                        ELSE 'unknown'
                    END as outcome
                FROM files
                {where_clause}
                ORDER BY outcome, path
                """
            )

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            rows_written = 0
            with output_path.open("w", newline="") as f:
                writer = csv.writer(f)
                # Write header
                writer.writerow(
                    [
                        "path",
                        "outcome",
                        "integrity_state",
                        "recovery_status",
                        "recovery_method",
                        "orig_duration",
                        "new_duration",
                        "duration_delta",
                        "pcm_md5",
                        "silence_events",
                        "backup_path",
                        "scanned_at",
                        "repaired_at",
                        "verified_at",
                    ]
                )

                for row in cursor:
                    writer.writerow(
                        [
                            row["path"],
                            row["outcome"],
                            row["integrity_state"],
                            row["recovery_status"],
                            row["recovery_method"],
                            row["duration"],
                            row["new_duration"],
                            row["duration_delta"],
                            row["pcm_md5"],
                            row["silence_events"],
                            row["backup_path"],
                            row["integrity_checked_at"],
                            row["recovered_at"],
                            row["verified_at"],
                        ]
                    )
                    rows_written += 1

            logger.info(f"Exported {rows_written} rows to {output_path}")
            return rows_written

        finally:
            conn.close()

    def export_json(self, output_path: Path, include_valid: bool = False) -> int:
        """
        Export detailed results to JSON.

        Args:
            output_path: Path for JSON output
            include_valid: Include files that passed initial validation

        Returns:
            Number of records written
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            where_clause = ""
            if not include_valid:
                where_clause = """
                WHERE integrity_state != 'valid'
                   OR recovery_status IS NOT NULL
                """

            cursor = conn.execute(
                f"""
                SELECT
                    path,
                    integrity_state,
                    recovery_status,
                    recovery_method,
                    duration,
                    new_duration,
                    duration_delta,
                    pcm_md5,
                    silence_events,
                    backup_path,
                    integrity_checked_at,
                    recovered_at,
                    verified_at
                FROM files
                {where_clause}
                ORDER BY path
                """
            )

            records = []
            for row in cursor:
                record = dict(row)
                # Compute outcome
                if record["integrity_state"] == "valid" and not record["recovery_status"]:
                    record["outcome"] = "valid"
                elif record["recovery_status"] in ("salvaged", "already_valid"):
                    record["outcome"] = "salvaged"
                elif record["recovery_status"] in ("failed", "verify_failed"):
                    record["outcome"] = "unrecoverable"
                elif record["recovery_status"] == "queued":
                    record["outcome"] = "pending_repair"
                else:
                    record["outcome"] = "unknown"
                records.append(record)

            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w") as f:
                json.dump(
                    {
                        "generated_at": datetime.now().isoformat(),
                        "summary": self.summary(),
                        "files": records,
                    },
                    f,
                    indent=2,
                )

            logger.info(f"Exported {len(records)} records to {output_path}")
            return len(records)

        finally:
            conn.close()

    def list_unrecoverable(self) -> list[str]:
        """
        Get list of unrecoverable file paths.

        Returns:
            List of file paths that could not be recovered
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT path FROM files
                WHERE recovery_status IN ('failed', 'verify_failed')
                ORDER BY path
                """
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def list_salvaged(self) -> list[str]:
        """
        Get list of successfully salvaged file paths.

        Returns:
            List of file paths that were successfully recovered
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT path FROM files
                WHERE recovery_status IN ('salvaged', 'already_valid')
                ORDER BY path
                """
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        stats = self.summary()

        print("\n" + "=" * 50)
        print("FLAC RECOVERY SUMMARY")
        print("=" * 50)
        print(f"Total files scanned:    {stats['total']:>8}")
        print("-" * 50)
        print(f"Valid (no repair):      {stats['valid']:>8}  ({stats.get('valid_pct', 0):.1f}%)")
        print(
            f"Salvaged:               {stats['salvaged']:>8}  ({stats.get('salvaged_pct', 0):.1f}%)")
        print(
            f"Unrecoverable:          {stats['unrecoverable']:>8}  ({stats.get('unrecoverable_pct', 0):.1f}%)")
        if stats["pending_repair"] > 0:
            print(f"Pending repair:         {stats['pending_repair']:>8}")
        print("=" * 50 + "\n")
