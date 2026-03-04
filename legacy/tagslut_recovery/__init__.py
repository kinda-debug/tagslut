"""
FLAC Recovery Module

Provides forensic recovery of corrupted FLAC files with:
- Scanning and validation (flac -t)
- FFmpeg-based salvage operations
- Post-repair verification
- Outcome reporting

Usage:
    from tagslut.recovery import RecoveryScanner, Repairer, Verifier, Reporter
"""

from .scanner import RecoveryScanner
from .repairer import Repairer
from .verifier import Verifier
from .reporter import Reporter

__all__ = ["RecoveryScanner", "Repairer", "Verifier", "Reporter"]
