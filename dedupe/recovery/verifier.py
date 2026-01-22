"""
Recovery Verifier Module

Post-repair verification with quality metrics:
- FLAC integrity re-check
- PCM MD5 hash (via FFmpeg)
- Silence detection
- Duration delta analysis
"""

import logging
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from dedupe.core.integrity import classify_flac_integrity

logger = logging.getLogger("dedupe.recovery")

DEFAULT_SILENCE_THRESHOLD = "-50dB"
DEFAULT_SILENCE_MIN_DURATION = 0.2


class Verifier:
    """
    Verifies repaired FLAC files and computes quality metrics.

    Checks:
    - flac -t passes
    - Duration change from original
    - PCM-level MD5 hash
    - Silence detection (potential dropouts)
    """

    def __init__(
        self,
        db_path: Path,
        silence_threshold: str = DEFAULT_SILENCE_THRESHOLD,
        silence_min_duration: float = DEFAULT_SILENCE_MIN_DURATION,
    ):
        self.db_path = Path(db_path)
        self.silence_threshold = silence_threshold
        self.silence_min_duration = silence_min_duration

    def verify_all(self) -> dict:
        """
        Verify all salvaged/repaired files.

        Returns:
            Summary dict with counts
        """
        files = self._get_verifiable_files()
        logger.info(f"Found {len(files)} files to verify")

        stats = {
            "total": len(files),
            "passed": 0,
            "degraded": 0,
            "failed": 0,
        }

        for row in files:
            file_path = row["path"]
            orig_duration = row["orig_duration"]
            result = self.verify_one(Path(file_path), orig_duration)

            if result["status"] == "passed":
                stats["passed"] += 1
            elif result["status"] == "degraded":
                stats["degraded"] += 1
            else:
                stats["failed"] += 1

        return stats

    def verify_one(
        self,
        file_path: Path,
        orig_duration: Optional[float] = None,
    ) -> dict:
        """
        Verify a single repaired file.

        Returns:
            Dict with verification results
        """
        file_path = Path(file_path)
        result = {
            "path": str(file_path),
            "status": "failed",
            "integrity": None,
            "new_duration": None,
            "duration_delta": None,
            "pcm_md5": None,
            "silence_events": None,
        }

        if not file_path.exists():
            logger.warning(f"File not found for verification: {file_path}")
            self._update_verification(file_path, result)
            return result

        # Check integrity
        integrity_state, _ = classify_flac_integrity(file_path)
        result["integrity"] = integrity_state

        if integrity_state != "valid":
            logger.warning(f"Verification failed - file still corrupt: {file_path}")
            self._update_verification(file_path, result)
            return result

        # Get new duration
        new_duration = self._get_duration(file_path)
        result["new_duration"] = new_duration

        # Compute duration delta
        if orig_duration and new_duration:
            result["duration_delta"] = new_duration - orig_duration

        # Compute PCM MD5
        result["pcm_md5"] = self._compute_pcm_md5(file_path)

        # Detect silence events
        result["silence_events"] = self._detect_silence(file_path)

        # Determine status
        # - passed: integrity OK, minimal duration change, no excessive silence
        # - degraded: integrity OK but quality concerns (duration loss, silence)
        if result["integrity"] == "valid":
            is_degraded = False

            # Check for significant duration loss (> 1 second)
            if result["duration_delta"] is not None and result["duration_delta"] < -1.0:
                logger.warning(
                    f"Duration loss detected: {result['duration_delta']:.2f}s for {file_path}"
                )
                is_degraded = True

            # Check for excessive silence events (> 10)
            if result["silence_events"] is not None and result["silence_events"] > 10:
                logger.warning(
                    f"Excessive silence events: {result['silence_events']} for {file_path}"
                )
                is_degraded = True

            result["status"] = "degraded" if is_degraded else "passed"

        self._update_verification(file_path, result)
        return result

    def _get_verifiable_files(self) -> list[dict]:
        """Get files with recovery_status in ('salvaged', 'already_valid')."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                """
                SELECT path, duration as orig_duration
                FROM files
                WHERE recovery_status IN ('salvaged', 'already_valid')
                  AND (pcm_md5 IS NULL OR verified_at IS NULL)
                ORDER BY path
                """
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

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

    def _compute_pcm_md5(self, file_path: Path) -> Optional[str]:
        """
        Compute MD5 of raw PCM audio data using FFmpeg.

        Uses FFmpeg to decode to raw PCM and pipes to md5sum.
        This is the GUI-free alternative to XLD.
        """
        try:
            # Decode to raw PCM and compute MD5
            ffmpeg = subprocess.Popen(
                [
                    "ffmpeg",
                    "-v", "error",
                    "-i", str(file_path),
                    "-f", "s16le",
                    "-acodec", "pcm_s16le",
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            md5sum = subprocess.Popen(
                ["md5sum"],
                stdin=ffmpeg.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            ffmpeg.stdout.close()
            output, _ = md5sum.communicate(timeout=120)

            if md5sum.returncode == 0:
                # md5sum output format: "hash  -"
                return output.decode().split()[0]

        except subprocess.TimeoutExpired:
            logger.warning(f"PCM MD5 timeout for {file_path}")
        except Exception as e:
            logger.warning(f"PCM MD5 failed for {file_path}: {e}")

        return None

    def _detect_silence(self, file_path: Path) -> Optional[int]:
        """
        Detect silence events using FFmpeg silencedetect filter.

        Returns count of silence_start events.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v", "error",
                    "-i", str(file_path),
                    "-af", f"silencedetect=n={self.silence_threshold}:d={self.silence_min_duration}",
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Count silence_start occurrences in stderr
            stderr = result.stderr
            count = stderr.count("silence_start")
            return count

        except subprocess.TimeoutExpired:
            logger.warning(f"Silence detection timeout for {file_path}")
        except Exception as e:
            logger.warning(f"Silence detection failed for {file_path}: {e}")

        return None

    def _update_verification(self, file_path: Path, result: dict) -> None:
        """Update verification results in database."""
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now().isoformat()

            # Map status to verify column
            verify_status = result["status"]  # passed, degraded, failed

            conn.execute(
                """
                UPDATE files SET
                    new_duration = ?,
                    duration_delta = ?,
                    pcm_md5 = ?,
                    silence_events = ?,
                    verified_at = ?,
                    recovery_status = CASE
                        WHEN recovery_status IN ('salvaged', 'already_valid')
                        THEN CASE ? WHEN 'failed' THEN 'verify_failed' ELSE recovery_status END
                        ELSE recovery_status
                    END
                WHERE path = ?
                """,
                (
                    result["new_duration"],
                    result["duration_delta"],
                    result["pcm_md5"],
                    result["silence_events"],
                    now,
                    verify_status,
                    str(file_path),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Get verification statistics from database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT
                    CASE
                        WHEN recovery_status = 'verify_failed' THEN 'failed'
                        WHEN verified_at IS NOT NULL AND duration_delta < -1.0 THEN 'degraded'
                        WHEN verified_at IS NOT NULL AND silence_events > 10 THEN 'degraded'
                        WHEN verified_at IS NOT NULL THEN 'passed'
                        ELSE 'pending'
                    END as status,
                    COUNT(*) as count
                FROM files
                WHERE recovery_status IN ('salvaged', 'already_valid', 'verify_failed')
                GROUP BY 1
                """
            )
            stats = {}
            for row in cursor:
                stats[row[0]] = row[1]
            return stats
        finally:
            conn.close()
