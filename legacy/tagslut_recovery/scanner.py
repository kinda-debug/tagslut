"""
Recovery Scanner Module

Scans FLAC files for integrity issues and records results in SQLite.
Reuses core/integrity.py for FLAC validation.
"""

import logging
import subprocess
import sqlite3
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional

from tagslut.core.integrity import classify_flac_integrity

logger = logging.getLogger("tagslut.recovery")

DEFAULT_TIMEOUT = 60  # seconds per file
DEFAULT_WORKERS = 4


class RecoveryScanner:
    """
    Scans FLAC files for integrity and records results to database.

    Uses flac -t for validation and ffprobe for duration extraction.
    Results are written atomically to SQLite.
    """

    def __init__(
        self,
        db_path: Path,
        workers: int = DEFAULT_WORKERS,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.db_path = Path(db_path)
        self.workers = workers
        self.timeout = timeout
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure recovery columns exist in files table."""
        conn = sqlite3.connect(self.db_path)
        try:
            # Add recovery-specific columns if they don't exist
            cursor = conn.execute("PRAGMA table_info(files)")
            existing = {row[1] for row in cursor.fetchall()}

            recovery_columns = {
                "recovery_status": "TEXT",
                "recovery_method": "TEXT",
                "backup_path": "TEXT",
                "recovered_at": "TEXT",
                "new_duration": "REAL",
                "duration_delta": "REAL",
                "pcm_md5": "TEXT",
                "silence_events": "INTEGER",
            }

            for col, col_type in recovery_columns.items():
                if col not in existing:
                    logger.info(f"Adding column {col} to files table")
                    conn.execute(f"ALTER TABLE files ADD COLUMN {col} {col_type}")

            conn.commit()
        finally:
            conn.close()

    def scan_directory(
        self,
        root: Path,
        incremental: bool = True,
    ) -> dict:  # type: ignore  # TODO: mypy-strict
        """
        Scan a directory for FLAC files.

        Args:
            root: Directory to scan
            incremental: Skip files already in database

        Returns:
            Summary dict with counts
        """
        root = Path(root)
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        flac_files = list(root.rglob("*.flac"))
        logger.info(f"Found {len(flac_files)} FLAC files in {root}")

        # Filter already-scanned files if incremental
        if incremental:
            flac_files = self._filter_unscanned(flac_files)
            logger.info(f"{len(flac_files)} files need scanning")

        if not flac_files:
            return {"total": 0, "valid": 0, "corrupt": 0, "recoverable": 0}

        stats = {"total": 0, "valid": 0, "corrupt": 0, "recoverable": 0}

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self._scan_one, f): f for f in flac_files
            }

            for future in futures:
                file_path = futures[future]
                try:
                    result = future.result(timeout=self.timeout)
                    stats["total"] += 1
                    stats[result["integrity_state"]] += 1
                except FuturesTimeoutError:
                    logger.warning(f"Timeout scanning {file_path}")
                    self._record_result(file_path, "corrupt", None, "timeout")
                    stats["total"] += 1
                    stats["corrupt"] += 1
                except Exception as e:
                    logger.error(f"Error scanning {file_path}: {e}")
                    self._record_result(file_path, "corrupt", None, str(e))
                    stats["total"] += 1
                    stats["corrupt"] += 1

        return stats

    def _filter_unscanned(self, files: list[Path]) -> list[Path]:
        """Filter out files already in the database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT path FROM files")
            existing = {row[0] for row in cursor.fetchall()}
            return [f for f in files if str(f) not in existing]
        finally:
            conn.close()

    def _scan_one(self, file_path: Path) -> dict:  # type: ignore  # TODO: mypy-strict
        """Scan a single file and record results."""
        integrity_state, error_msg = classify_flac_integrity(file_path)
        duration = self._get_duration(file_path)

        self._record_result(file_path, integrity_state, duration, error_msg)

        return {
            "path": str(file_path),
            "integrity_state": integrity_state,
            "duration": duration,
            "error": error_msg,
        }

    def _get_duration(self, file_path: Path) -> Optional[float]:
        """Extract duration using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError) as e:
            logger.warning(f"Could not get duration for {file_path}: {e}")
        return None

    def _record_result(
        self,
        file_path: Path,
        integrity_state: str,
        duration: Optional[float],
        error_msg: Optional[str] = None,
    ) -> None:
        """Record scan result to database."""
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().isoformat()
            size = file_path.stat().st_size if file_path.exists() else None
            mtime = file_path.stat().st_mtime if file_path.exists() else None

            # Set recovery_status based on integrity
            recovery_status = None
            if integrity_state in ("corrupt", "recoverable"):
                recovery_status = "queued"

            conn.execute(
                """
                INSERT INTO files (
                    path, integrity_state, integrity_checked_at,
                    duration, size, mtime, recovery_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    integrity_state = excluded.integrity_state,
                    integrity_checked_at = excluded.integrity_checked_at,
                    duration = COALESCE(excluded.duration, duration),
                    recovery_status = CASE
                        WHEN excluded.integrity_state IN ('corrupt', 'recoverable')
                        THEN 'queued'
                        ELSE NULL
                    END
                """,
                (str(file_path), integrity_state, now, duration, size, mtime, recovery_status),
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:  # type: ignore  # TODO: mypy-strict
        """Get current scan statistics from database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    integrity_state,
                    COUNT(*) as count
                FROM files
                WHERE integrity_state IS NOT NULL
                GROUP BY integrity_state
                """
            )
            stats = {"valid": 0, "corrupt": 0, "recoverable": 0}
            for row in cursor:
                if row[0] in stats:
                    stats[row[0]] = row[1]
            stats["total"] = sum(stats.values())
            return stats
        finally:
            conn.close()
