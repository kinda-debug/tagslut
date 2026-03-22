from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional, List, Dict, Any, cast

from tagslut.zones import Zone, coerce_zone

IntegrityState = Literal["valid", "recoverable", "corrupt"]
DJ_SET_ROLES = frozenset({"groove", "prime", "bridge", "club"})
_DJ_SET_ROLE_PRIORITY = ("groove", "prime", "bridge", "club")
DJ_SET_ROLE_ORDER = tuple(role for role in _DJ_SET_ROLE_PRIORITY if role in DJ_SET_ROLES) + tuple(
    sorted(DJ_SET_ROLES.difference(_DJ_SET_ROLE_PRIORITY))
)
DJ_SUBROLES = frozenset({
    "opener", "builder", "vocal", "left_turn",
    "closer", "classic", "tool"
})


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
    # Management/Inventory fields
    download_source: Optional[str] = None
    download_date: Optional[str] = None
    original_path: Optional[Path] = None
    mgmt_status: Optional[str] = None
    fingerprint: Optional[str] = None
    m3u_exported: Optional[str] = None
    m3u_path: Optional[str] = None
    is_dj_material: Optional[int] = None
    dj_set_role: Optional[str] = None
    dj_subrole: Optional[str] = None
    duration_ref_ms: Optional[int] = None
    duration_ref_source: Optional[str] = None
    duration_ref_track_id: Optional[str] = None
    duration_ref_updated_at: Optional[str] = None
    duration_measured_ms: Optional[int] = None
    duration_measured_at: Optional[str] = None
    duration_delta_ms: Optional[int] = None
    duration_status: Optional[str] = None
    duration_check_version: Optional[str] = None

    def __post_init__(self) -> None:
        # Ensure path is always a Path object
        if isinstance(self.path, str):
            self.path = Path(self.path)
        # Ensure original_path is a Path object if provided
        if isinstance(self.original_path, str):
            self.original_path = Path(self.original_path)
        # Normalize tuple/list values for scalar fields
        self.acoustid = self._normalize_scalar(self.acoustid)
        self.integrity_state = self._normalize_integrity_state(self.integrity_state)
        self.download_source = self._normalize_scalar(self.download_source)
        self.mgmt_status = self._normalize_scalar(self.mgmt_status)
        self.fingerprint = self._normalize_scalar(self.fingerprint)
        self.m3u_exported = self._normalize_scalar(self.m3u_exported)
        self.m3u_path = self._normalize_scalar(self.m3u_path)
        self.duration_ref_source = self._normalize_scalar(self.duration_ref_source)
        self.duration_ref_track_id = self._normalize_scalar(self.duration_ref_track_id)
        self.duration_ref_updated_at = self._normalize_scalar(self.duration_ref_updated_at)
        self.duration_measured_at = self._normalize_scalar(self.duration_measured_at)
        self.duration_status = self._normalize_scalar(self.duration_status)
        self.duration_check_version = self._normalize_scalar(self.duration_check_version)
        if self.zone is not None:
            self.zone = coerce_zone(self.zone)
        if self.dj_set_role is not None and self.dj_set_role not in DJ_SET_ROLES:
            raise ValueError(
                f"Invalid dj_set_role {self.dj_set_role!r}. "
                f"Allowed: {sorted(DJ_SET_ROLES)}"
            )
        if self.dj_subrole is not None and self.dj_subrole not in DJ_SUBROLES:
            raise ValueError(
                f"Invalid dj_subrole {self.dj_subrole!r}. "
                f"Allowed: {sorted(DJ_SUBROLES)}"
            )

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


@dataclass
class GigSet:
    """
    A named collection of tracks assembled for a specific gig or set.
    """
    name: str
    id: Optional[int] = None
    filter_expr: Optional[str] = None
    usb_path: Optional[str] = None
    manifest_path: Optional[str] = None
    track_count: int = 0
    created_at: Optional[str] = None
    exported_at: Optional[str] = None


@dataclass
class GigSetTrack:
    """
    A single track within a GigSet, tracking its MP3 and USB export state.
    """
    gig_set_id: int
    file_path: Path
    id: Optional[int] = None
    mp3_path: Optional[Path] = None
    usb_dest_path: Optional[Path] = None
    transcoded_at: Optional[str] = None
    exported_at: Optional[str] = None
    rekordbox_id: Optional[int] = None

    def __post_init__(self) -> None:
        if isinstance(self.file_path, str):
            self.file_path = Path(self.file_path)
        if isinstance(self.mp3_path, str):
            self.mp3_path = Path(self.mp3_path)
        if isinstance(self.usb_dest_path, str):
            self.usb_dest_path = Path(self.usb_dest_path)


@dataclass
class ScanRun:
    library_root: Path
    mode: str = "initial"
    id: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    tool_versions_json: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.library_root, str):
            self.library_root = Path(self.library_root)


@dataclass
class ScanQueueItem:
    run_id: int
    path: Path
    id: Optional[int] = None
    size_bytes: Optional[int] = None
    mtime_ns: Optional[int] = None
    stage: int = 0
    state: str = "PENDING"
    last_error: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class ScanIssue:
    run_id: int
    path: Path
    issue_code: str
    severity: str
    evidence_json: str
    id: Optional[int] = None
    checksum: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            self.path = Path(self.path)


@dataclass
class FileMetadataArchive:
    checksum: str
    first_seen_at: str
    first_seen_path: Path
    raw_tags_json: str
    technical_json: str
    durations_json: str
    isrc_candidates_json: str
    identity_confidence: int
    fingerprint_json: Optional[str] = None
    quality_rank: Optional[int] = None

    def __post_init__(self) -> None:
        if isinstance(self.first_seen_path, str):
            self.first_seen_path = Path(self.first_seen_path)
