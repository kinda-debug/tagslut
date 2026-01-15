"""IO wait detection and volume monitoring."""

import os
import subprocess
from typing import Dict, Optional
import logging
from dataclasses import dataclass
import psutil

logger = logging.getLogger(__name__)


@dataclass
class DiskIOStats:
    """Disk IO statistics."""
    read_count: int
    write_count: int
    read_bytes: int
    write_bytes: int
    read_time: int
    write_time: int


class IOMonitor:
    """Monitor IO performance and detect stalls."""
    
    def __init__(self, check_interval: int = 5):
        self.check_interval = check_interval
        self._last_io_time = None
        self._stall_detected = False
    
    def get_disk_io_stats(self, device: str = "/") -> Optional[DiskIOStats]:
        """Get disk IO statistics."""
        try:
            stats = psutil.disk_io_counters(perdisk=False)
            if stats:
                return DiskIOStats(
                    read_count=stats.read_count,
                    write_count=stats.write_count,
                    read_bytes=stats.read_bytes,
                    write_bytes=stats.write_bytes,
                    read_time=stats.read_time,
                    write_time=stats.write_time,
                )
        except Exception as e:
            logger.error(f"Failed to get IO stats: {e}")
        return None
    
    def check_io_activity(self) -> bool:
        """Check if IO activity is occurring."""
        try:
            current = self.get_disk_io_stats()
            if current and self._last_io_time:
                # If read/write counts changed, IO is active
                if (current.read_count > self._last_io_time.read_count or
                    current.write_count > self._last_io_time.write_count):
                    self._stall_detected = False
                    return True
            self._last_io_time = current
            return False
        except Exception as e:
            logger.error(f"IO activity check failed: {e}")
            return False
    
    def get_mount_status(self, mount_point: str) -> Dict[str, bool]:
        """Get mount status for path."""
        try:
            return {
                "is_mount": os.path.ismount(mount_point),
                "exists": os.path.exists(mount_point),
                "readable": os.access(mount_point, os.R_OK),
                "writable": os.access(mount_point, os.W_OK),
            }
        except (OSError, IOError) as e:
            logger.error(f"Mount status check failed: {e}")
            return {"error": True}
