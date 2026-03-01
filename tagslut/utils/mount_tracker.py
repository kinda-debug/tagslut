"""Track volume mount state across operations."""

import os
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class MountState:
    """Immutable mount state snapshot."""
    timestamp: datetime
    volume_path: str
    is_mounted: bool
    is_readable: bool
    is_writable: bool
    filesystem_type: Optional[str] = None


class MountTracker:
    """Track mount state before and during operations."""

    def __init__(self, volume_path: str):
        self.volume_path = volume_path
        self._initial_state: Optional[MountState] = None
        self._current_state: Optional[MountState] = None

    def capture_state(self) -> MountState:
        """Capture current mount state."""
        return MountState(
            timestamp=datetime.utcnow(),
            volume_path=self.volume_path,
            is_mounted=os.path.ismount(self.volume_path),
            is_readable=os.access(self.volume_path, os.R_OK),
            is_writable=os.access(self.volume_path, os.W_OK),
        )

    def start_operation(self) -> bool:
        """Capture initial mount state before operation."""
        self._initial_state = self.capture_state()
        return self._initial_state.is_mounted and self._initial_state.is_readable

    def check_mount_status(self) -> bool:
        """Check if volume is still in expected state."""
        current = self.capture_state()
        self._current_state = current

        if self._initial_state is None:
            return current.is_mounted

        # Check if mount state changed
        if current.is_mounted != self._initial_state.is_mounted:
            return False

        # Check if readability changed
        if current.is_readable != self._initial_state.is_readable:
            return False

        return True

    def get_state_change_log(self) -> Dict:  # type: ignore  # TODO: mypy-strict
        """Log mount state changes."""
        if not self._initial_state or not self._current_state:
            return {}

        return {
            'initial': {
                'mounted': self._initial_state.is_mounted,
                'readable': self._initial_state.is_readable,
                'writable': self._initial_state.is_writable,
            },
            'current': {
                'mounted': self._current_state.is_mounted,
                'readable': self._current_state.is_readable,
                'writable': self._current_state.is_writable,
            },
            'changed': (
                self._initial_state.is_mounted != self._current_state.is_mounted or
                self._initial_state.is_readable != self._current_state.is_readable
            ),
        }
