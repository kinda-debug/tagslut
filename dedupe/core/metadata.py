import logging
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
    flac_ok = False
    integrity_state: IntegrityState = "corrupt"
    checksum = "NOT_SCANNED"
    duration = 0.0
    bit_depth = 0
    sample_rate = 0
    bitrate = 0
    tags: Dict[str, Any] = {}

    # Optional expensive integrity check (Phase 3, for winners)
    if scan_integrity:
        integrity_state = classify_flac_integrity(path_obj)
        flac_ok = (integrity_state == "valid")

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
            streaminfo_md5 = getattr(audio.info, 'md5_signature', None)
            if streaminfo_md5:
                # Convert bytes to hex string if needed
                if isinstance(streaminfo_md5, bytes):
                    streaminfo_md5 = streaminfo_md5.hex()
                checksum = f"streaminfo:{streaminfo_md5}"
            elif scan_hash:
                # Fall back to full-file hash only if explicitly requested
                checksum = calculate_file_hash(path_obj)
        
        # Tag extraction
        if audio.tags:
            tags = {k.lower(): v[0] if isinstance(v, list) and len(v) == 1 else v 
                    for k, v in audio.tags.items()}

        # If we didn't run explicit integrity check, standard load implies basic header health
        if not scan_integrity:
            integrity_state = "valid"
            flac_ok = True 

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
        duration=duration,
        bit_depth=bit_depth,
        sample_rate=sample_rate,
        bitrate=bitrate,
        metadata=tags,
        flac_ok=flac_ok,
        integrity_state=integrity_state
    )
