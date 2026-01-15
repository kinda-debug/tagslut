"""Mount state logging at scan initialization.

Implements Item 9: Mount state logged at scan init
"""
import subprocess
import logging
from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class MountPoint:
    device: str
    mount_path: str
    filesystem: str
    total_size: int
    available_size: int
    timestamp: str

class MountStateLogger:
    """Log filesystem mount state at scan initialization."""
    
    def __init__(self):
        self.mount_points: List[MountPoint] = []
        self.scan_start_time = datetime.now().isoformat()
    
    def log_mount_state(self) -> List[MountPoint]:
        """Capture and log current mount state."""
        try:
            # Use df command to get mount information
            result = subprocess.run(
                ['df', '-h'],
                capture_output=True,
                text=True
            )
            
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 6:
                    mount = MountPoint(
                        device=parts[0],
                        mount_path=parts[5],
                        filesystem=parts[0].split('/')[-1],
                        total_size=self._parse_size(parts[1]),
                        available_size=self._parse_size(parts[3]),
                        timestamp=self.scan_start_time
                    )
                    self.mount_points.append(mount)
                    logger.info(f"Mounted: {mount.mount_path} ({mount.available_size} available)")
        except Exception as e:
            logger.error(f"Failed to log mount state: {e}")
        
        return self.mount_points
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string (e.g., '1.5G') to bytes."""
        multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
        try:
            for suffix, mult in multipliers.items():
                if size_str.endswith(suffix):
                    return int(float(size_str[:-1]) * mult)
            return int(float(size_str))
        except:
            return 0
    
    def get_summary(self) -> Dict:
        """Get mount state summary."""
        return {
            "scan_start": self.scan_start_time,
            "mount_count": len(self.mount_points),
            "total_available": sum(m.available_size for m in self.mount_points),
            "mounts": [{
                "device": m.device,
                "path": m.mount_path,
                "available_gb": m.available_size / (1024**3)
            } for m in self.mount_points]
        }
