"""
Recovery Repairer Module

Attempts to salvage corrupted FLAC files using FFmpeg.
Move-only policy: no backups are created; temporary outputs are removed after success.
"""

import logging
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from tagslut.core.integrity import classify_flac_integrity

logger = logging.getLogger("tagslut.recovery")

DEFAULT_COMPRESSION = 5
DEFAULT_TIMEOUT = 300  # 5 minutes for repair operations


class Repairer:
    """
    Repairs corrupted FLAC files using FFmpeg salvage.

    Process:
    1. Query database for files with recovery_status='queued'
    2. Attempt FFmpeg salvage with error tolerance
    3. Validate output with flac -t
    4. Replace original if successful
    5. Update database state
    """

    def __init__(
        self,
        db_path: Path,
        compression_level: int = DEFAULT_COMPRESSION,
        timeout: int = DEFAULT_TIMEOUT,
        dry_run: bool = True,
    ):
        """
        Initialize the repairer.

        Args:
            db_path: Path to SQLite database
            compression_level: FLAC compression level (0-8)
            timeout: Timeout for FFmpeg operations in seconds
            dry_run: If True, don't actually modify files
        """
        self.db_path = Path(db_path)
        self.compression_level = compression_level
        self.timeout = timeout
        self.dry_run = dry_run
        if not dry_run:
            logger.info("Move-only mode: backups are not created (use external backups).")

    def repair_all(self) -> dict:  # type: ignore  # TODO: mypy-strict
        """
        Repair all queued files.

        Returns:
            Summary dict with counts
        """
        queued = self._get_queued_files()
        logger.info(f"Found {len(queued)} files queued for repair")

        stats = {
            "total": len(queued),
            "salvaged": 0,
            "already_valid": 0,
            "failed": 0,
            "skipped": 0,
        }

        for file_path in queued:
            result = self.repair_one(Path(file_path))
            if result == "salvaged":
                stats["salvaged"] += 1
            elif result == "already_valid":
                stats["already_valid"] += 1
            elif result == "failed":
                stats["failed"] += 1
            else:
                stats["skipped"] += 1

        return stats

    def repair_one(self, file_path: Path) -> str:
        """
        Attempt to repair a single file.

        Returns:
            Status string: 'salvaged', 'already_valid', 'failed', 'skipped'
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            self._update_status(file_path, "failed", error="file_not_found")
            return "failed"

        # Check if file is actually corrupt
        integrity_state, _ = classify_flac_integrity(file_path)
        if integrity_state == "valid":
            logger.info(f"File already valid: {file_path}")
            self._update_status(file_path, "already_valid", method="none")
            return "already_valid"

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would repair: {file_path}")
            return "skipped"

        # Attempt FFmpeg salvage
        temp_path = file_path.with_suffix(".ffmpeg_tmp.flac")
        try:
            success = self._ffmpeg_salvage(file_path, temp_path)

            if success:
                # Validate the repaired file
                new_state, _ = classify_flac_integrity(temp_path)
                if new_state == "valid":
                    # Replace original with repaired version
                    temp_path.replace(file_path)
                    logger.info(f"Salvaged: {file_path}")
                    self._update_status(
                        file_path,
                        "salvaged",
                        method="ffmpeg",
                    )
                    return "salvaged"
                else:
                    logger.warning(f"Repaired file still invalid: {file_path}")

            # Cleanup failed attempt
            if temp_path.exists():
                temp_path.unlink()

            self._update_status(file_path, "failed", error="repair_invalid")
            return "failed"

        except Exception as e:
            logger.error(f"Repair failed for {file_path}: {e}")
            if temp_path.exists():
                temp_path.unlink()
            self._update_status(file_path, "failed", error=str(e))
            return "failed"

    def _get_queued_files(self) -> list[str]:
        """Get files with recovery_status='queued'."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT path FROM files
                WHERE recovery_status = 'queued'
                ORDER BY path
                """
            )
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def _ffmpeg_salvage(self, input_path: Path, output_path: Path) -> bool:
        """
        Attempt FFmpeg salvage with error tolerance.

        Uses -err_detect ignore_err to skip corrupt frames.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v", "error",
                    "-err_detect", "ignore_err",
                    "-i", str(input_path),
                    "-map", "0:a",
                    "-c:a", "flac",
                    "-compression_level", str(self.compression_level),
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            # FFmpeg may return non-zero but still produce valid output
            if output_path.exists() and output_path.stat().st_size > 0:
                return True

            if result.returncode != 0:
                logger.debug(f"FFmpeg stderr: {result.stderr}")

            return False

        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for {input_path}")
            return False
        except Exception as e:
            logger.error(f"FFmpeg error for {input_path}: {e}")
            return False

    def _update_status(
        self,
        file_path: Path,
        status: str,
        method: Optional[str] = None,
        backup_path: Optional[Path] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update recovery status in database."""
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().isoformat()
            conn.execute(
                """
                UPDATE files SET
                    recovery_status = ?,
                    recovery_method = ?,
                    backup_path = ?,
                    recovered_at = ?
                WHERE path = ?
                """,
                (
                    status,
                    method,
                    str(backup_path) if backup_path else None,
                    now if status in ("salvaged", "already_valid", "failed") else None,
                    str(file_path),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:  # type: ignore  # TODO: mypy-strict
        """Get current repair statistics from database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    recovery_status,
                    COUNT(*) as count
                FROM files
                WHERE recovery_status IS NOT NULL
                GROUP BY recovery_status
                """
            )
            stats = {}
            for row in cursor:
                stats[row[0]] = row[1]
            return stats
        finally:
            conn.close()

    def cleanup_backups(self, verified_only: bool = True) -> dict:  # type: ignore  # TODO: mypy-strict
        """
        Backups are not created in move-only mode.
        This method is retained for compatibility and always no-ops.
        """
        if self.dry_run:
            logger.info("[DRY-RUN] No backups to clean up (move-only mode)")
        else:
            logger.info("No backups to clean up (move-only mode)")
        return {"deleted": 0, "failed": 0, "skipped": 0}
