from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any

IntegrityState = Literal["valid", "recoverable", "corrupt"]
Zone = Literal["inbox", "staging", "accepted", "rejected", "suspect", "quarantine"]

@dataclass
class AudioFile:
    """
    Canonical representation of a FLAC file in the system.
    """
    path: Path
    checksum: str
    duration: float
    bit_depth: int
    sample_rate: int
    bitrate: int
    metadata: Dict[str, Any]
    flac_ok: bool
    library: Optional[str] = None
    zone: Optional[Zone] = None
    mtime: Optional[float] = None
    size: Optional[int] = None
    acoustid: Optional[str] = None
    integrity_state: Optional[IntegrityState] = None

    def __post_init__(self):
        # Ensure path is always a Path object
        if isinstance(self.path, str):
            self.path = Path(self.path)

@dataclass
class DuplicateGroup:
    """
    Represents a group of potential duplicates identified by a specific strategy.
    """
    group_id: str
    files: List[AudioFile]
    similarity: float
    source: Literal["checksum", "acoustid", "dupeguru"]

@dataclass
class Decision:
    """
    A concrete action to be taken on a specific file.
    """
    file: AudioFile
    action: Literal["KEEP", "DROP", "REVIEW"]
    reason: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    evidence: Dict[str, Any] = field(default_factory=dict)
