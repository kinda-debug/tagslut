"""Real-time progress tracking with ETA calculation."""

import time
import os
from dataclasses import dataclass, field
from typing import Optional, Dict
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class ThroughputMetrics:
    """Track operation throughput."""
    files_processed: int = 0
    bytes_processed: int = 0
    start_time: float = field(default_factory=time.time)

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def files_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        return self.files_processed / elapsed if elapsed > 0 else 0

    @property
    def mb_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        mb = self.bytes_processed / (1024 * 1024)
        return mb / elapsed if elapsed > 0 else 0


@dataclass
class ProgressSnapshot:
    """Immutable snapshot of progress state."""
    current_file: str
    files_completed: int
    total_files: int
    eta_seconds: Optional[float]
    files_per_second: float
    mb_per_second: float


class ProgressTracker:
    """Real-time progress tracking for file operations."""

    def __init__(self, total_files: int, total_bytes: int = 0, timeout_seconds: int = 3600):
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.timeout_seconds = timeout_seconds
        self.metrics = ThroughputMetrics()
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._current_file: Optional[str] = None
        self._start_time = time.time()
        self._io_stalls = 0

    def update(self, file_path: str, bytes_processed: int = 0) -> None:
        """Update progress."""
        with self._lock:
            self._current_file = file_path
            self._last_activity = time.time()
            self.metrics.files_processed += 1
            self.metrics.bytes_processed += bytes_processed

    def check_timeout(self) -> bool:
        """Check if timeout exceeded."""
        elapsed = time.time() - self._start_time
        return elapsed > self.timeout_seconds

    def check_io_stall(self, threshold: int = 30) -> bool:
        """Detect IO stall (no activity > threshold seconds)."""
        idle = time.time() - self._last_activity
        if idle > threshold:
            self._io_stalls += 1
            logger.warning(f"IO stall detected: {idle:.1f}s at {self._current_file}")
            return True
        return False

    def get_snapshot(self) -> ProgressSnapshot:
        """Get progress snapshot."""
        with self._lock:
            eta_seconds = None
            if self.metrics.files_per_second > 0:
                remaining = self.total_files - self.metrics.files_processed
                eta_seconds = remaining / self.metrics.files_per_second

            return ProgressSnapshot(
                current_file=self._current_file or "init",
                files_completed=self.metrics.files_processed,
                total_files=self.total_files,
                eta_seconds=eta_seconds,
                files_per_second=self.metrics.files_per_second,
                mb_per_second=self.metrics.mb_per_second,
            )


class VolumeStateValidator:
    """Validate volume mount state."""

    @staticmethod
    def check_volume_mounted(volume_path: str) -> bool:
        """Check if volume is mounted."""
        try:
            return os.path.ismount(volume_path) or os.path.exists(volume_path)
        except (OSError, IOError) as e:
            logger.error(f"Mount check failed for {volume_path}: {e}")
            return False

    @staticmethod
    def check_write_sanity(volume_path: str, min_free_gb: int = 1) -> bool:
        """Check write capability and free space."""
        try:
            if not os.path.exists(volume_path):
                return False
            stat = os.statvfs(volume_path)
            available = stat.f_bavail * stat.f_frsize
            min_bytes = min_free_gb * 1024 * 1024 * 1024
            return available > min_bytes
        except (OSError, IOError) as e:
            logger.error(f"Write sanity check failed: {e}")
            return False

    @staticmethod
    def preflight_check(source_root: str, dest_root: Optional[str] = None) -> Dict[str, bool]:
        """Run preflight validation checks."""
        results = {
            "source_mounted": VolumeStateValidator.check_volume_mounted(source_root),
            "source_readable": os.access(source_root, os.R_OK),
        }
        if dest_root:
            results["dest_mounted"] = VolumeStateValidator.check_volume_mounted(dest_root)
            results["dest_writable"] = VolumeStateValidator.check_write_sanity(dest_root)
        return results
