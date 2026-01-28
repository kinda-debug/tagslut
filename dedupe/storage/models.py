from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any, cast

from dedupe.utils.zones import Zone, coerce_zone

IntegrityState = Literal["valid", "recoverable", "corrupt"]


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
    flac_ok: Optional[bool] = None
    streaminfo_md5: Optional[str] = None
    sha256: Optional[str] = None
    library: Optional[str] = None
    zone: Optional[Zone] = None
    mtime: Optional[float] = None
    size: Optional[int] = None
    acoustid: Optional[str] = None
    integrity_state: Optional[IntegrityState] = None
    integrity_checked_at: Optional[str] = None
    streaminfo_checked_at: Optional[str] = None
    sha256_checked_at: Optional[str] = None
    checksum_type: Optional[str] = None

    def __post_init__(self) -> None:
        # Ensure path is always a Path object
        if isinstance(self.path, str):
            self.path = Path(self.path)
        # Normalize tuple/list values for scalar fields
        self.acoustid = self._normalize_scalar(self.acoustid)
        self.integrity_state = self._normalize_integrity_state(self.integrity_state)
        if self.zone is not None:
            self.zone = coerce_zone(self.zone)  # type: ignore[assignment]

    @staticmethod
    def _normalize_scalar(value: Optional[object]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            for item in value:
                if item is None:
                    continue
                if isinstance(item, str):
                    return item
                return str(item)
            return None
        return str(value)

    @staticmethod
    def _normalize_integrity_state(value: Optional[object]) -> Optional[IntegrityState]:
        scalar = AudioFile._normalize_scalar(value)
        allowed: frozenset[str] = frozenset({"valid", "recoverable", "corrupt"})
        if scalar and scalar in allowed:
            return cast(IntegrityState, scalar)
        return None


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
