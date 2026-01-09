import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

import mutagen
from mutagen.flac import FLAC, FLACNoHeaderError

from dedupe.storage.models import AudioFile
from dedupe.core.integrity import classify_flac_integrity, IntegrityState
from dedupe.core.hashing import calculate_file_hash

logger = logging.getLogger("dedupe")

def extract_metadata(
    file_path: Path,
    scan_integrity: bool = False,
    scan_hash: bool = False,
    library: str | None = None,
    zone: str | None = None,
) -> AudioFile:
    """
    Extracts technical and tag metadata from a FLAC file and returns a populated AudioFile.

    Hashing strategy (3-phase approach):
    - Phase 1 (default): Uses FLAC STREAMINFO MD5 (fast, embedded)
    - Phase 2: Clustering uses streaminfo_md5 + duration + sample rate
    - Phase 3: Full-file SHA256 only if scan_hash=True (for winners)

    Args:
        file_path: Path to the FLAC file.
        scan_integrity: If True, runs `flac -t` immediately (expensive).
        scan_hash: If True, calculates full-file SHA-256 (expensive, for winners only).
        library: Library tag (e.g. "recovery", "vault", "bad").
        zone: Zone tag (e.g. "accepted", "suspect", "quarantine").

    Returns:
        AudioFile object with checksum populated as:
        - "streaminfo:<hex>" if STREAMINFO MD5 available (Phase 1)
        - "sha256:<hex>" if scan_hash=True (Phase 3)
        - "NOT_SCANNED" if neither available

    Raises:
        ValueError: If file is not a valid FLAC or cannot be read.
    """
    path_obj = Path(file_path)

    # Cheap stat info for incremental scans / observability
    try:
        st = path_obj.stat()
        mtime = st.st_mtime
        size = st.st_size
    except OSError as e:
        raise ValueError(f"Cannot stat file {path_obj}: {e}")

    # Defaults
    # Note: We no longer hash here by default - streaminfo MD5 is extracted from FLAC metadata
    # Only run expensive full-file hash if scan_hash=True (Phase 3, for winners)
    flac_ok: bool | None = None
    integrity_state: IntegrityState | None = None
    checksum = "NOT_SCANNED"
    checksum_type: str | None = None
    streaminfo_md5: str | None = None
    sha256: str | None = None
    integrity_checked_at: str | None = None
    streaminfo_checked_at: str | None = None
    sha256_checked_at: str | None = None
    duration = 0.0
    bit_depth = 0
    sample_rate = 0
    bitrate = 0
    tags: Dict[str, Any] = {}
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Optional expensive integrity check (Phase 3, for winners)
    if scan_integrity:
        integrity_state, _ = classify_flac_integrity(path_obj)
        flac_ok = (integrity_state == "valid")
        integrity_checked_at = now_iso

    try:
        audio = FLAC(path_obj)

        # Technical details
        if audio.info:
            duration = getattr(audio.info, 'length', 0.0)
            bit_depth = getattr(audio.info, 'bits_per_sample', 0)
            sample_rate = getattr(audio.info, 'sample_rate', 0)
            bitrate = getattr(audio.info, 'bitrate', 0)

            # Extract STREAMINFO MD5 (fast, embedded in FLAC metadata block)
            # This is NOT the file hash - it's the hash of the decoded audio
            # Perfect for fast duplicate detection without full-file hashing
            streaminfo_md5 = getattr(audio.info, "md5_signature", None)
            if streaminfo_md5:
                # Normalize mutagen return types (bytes/int) to a hex string
                if isinstance(streaminfo_md5, (bytes, bytearray)):
                    streaminfo_md5 = streaminfo_md5.hex()
                elif isinstance(streaminfo_md5, int):
                    streaminfo_md5 = f"{streaminfo_md5:032x}"
                else:
                    streaminfo_md5 = str(streaminfo_md5)
                checksum = f"streaminfo:{streaminfo_md5}"
                checksum_type = "STREAMINFO_MD5"
                streaminfo_checked_at = now_iso

            if scan_hash:
                sha256 = calculate_file_hash(path_obj)
                sha256_checked_at = now_iso
                if not streaminfo_md5:
                    checksum = sha256
                    checksum_type = "SHA256_FULL"
                else:
                    # If we have both, SHA256 is the authoritative evidence for the AudioFile.checksum
                    checksum = sha256
                    checksum_type = "SHA256_FULL"

        # Tag extraction
        if audio.tags:
            # Convert ALL mutagen objects to plain Python types
            # Mutagen returns special list/tuple subclasses that SQLite can't bind
            tags = {}
            for k, v in audio.tags.items():
                # Handle list-like values
                if isinstance(v, (list, tuple)):
                    # Convert to plain list, and convert each item to str/int/float
                    plain_list = [str(item) if not isinstance(item, (int, float)) else item for item in v]
                    if len(plain_list) == 1:
                        tags[k.lower()] = plain_list[0]
                    else:
                        tags[k.lower()] = plain_list
                # Handle other types - convert to plain Python types
                else:
                    # Convert to str if it's a mutagen-specific type
                    if type(v).__module__.startswith('mutagen'):
                        tags[k.lower()] = str(v)
                    else:
                        tags[k.lower()] = v

        # If we didn't run explicit integrity check, standard load implies basic header health
    except FLACNoHeaderError:
        logger.error(f"No FLAC header found: {path_obj}")
        integrity_state = "corrupt"
        flac_ok = False
    except mutagen.MutagenError as e:
        logger.error(f"Mutagen error reading {path_obj}: {e}")
        integrity_state = "corrupt"
        flac_ok = False
    except Exception as e:
        logger.error(f"Unexpected error reading metadata for {path_obj}: {e}")
        raise ValueError(f"Failed to read metadata: {e}")

    return AudioFile(
        path=path_obj,
        library=library,
        zone=zone,
        mtime=mtime,
        size=size,
        checksum=checksum,
        streaminfo_md5=streaminfo_md5,
        sha256=sha256,
        duration=duration,
        bit_depth=bit_depth,
        sample_rate=sample_rate,
        bitrate=bitrate,
        metadata=tags,
        flac_ok=flac_ok,
        integrity_state=integrity_state,
        integrity_checked_at=integrity_checked_at,
        streaminfo_checked_at=streaminfo_checked_at,
        sha256_checked_at=sha256_checked_at,
        checksum_type=checksum_type,
    )
