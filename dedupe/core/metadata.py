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

    Args:
        file_path: Path to the FLAC file.
        scan_integrity: If True, runs `flac -t` immediately (expensive).
        scan_hash: If True, calculates SHA-256 immediately (expensive).

    Returns:
        AudioFile object.
    
    Raises:
        ValueError: If file is not a valid FLAC or cannot be read.
    """
    path_obj = Path(file_path)

    # Cheap stat info for incremental scans / observability
    try:
        st = path_obj.stat()
        mtime = float(st.st_mtime)
        size = int(st.st_size)
    except Exception:
        mtime = None
        size = None
    
    # Defaults
    flac_ok = False
    integrity_state: IntegrityState = "corrupt"
    checksum = "NOT_SCANNED"
    duration = 0.0
    bit_depth = 0
    sample_rate = 0
    bitrate = 0
    tags: Dict[str, Any] = {}

    # Optional expensive checks
    if scan_integrity:
        integrity_state, _ = classify_flac_integrity(path_obj)
        flac_ok = integrity_state == "valid"
    
    if scan_hash:
        checksum = calculate_file_hash(path_obj)

    try:
        audio = FLAC(path_obj)
        
        # Technical details
        if audio.info:
            duration = getattr(audio.info, 'length', 0.0)
            bit_depth = getattr(audio.info, 'bits_per_sample', 0)
            sample_rate = getattr(audio.info, 'sample_rate', 0)
            bitrate = getattr(audio.info, 'bitrate', 0)
        
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
