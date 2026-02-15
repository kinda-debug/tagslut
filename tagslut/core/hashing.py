import hashlib
import logging
from pathlib import Path

DEFAULT_PREHASH_BYTES = 4 * 1024 * 1024

logger = logging.getLogger("tagslut")

def calculate_file_hash(file_path: Path, block_size: int = 65536) -> str:
    """
    Calculates the SHA-256 checksum of a file's content.
    Used for strict deduplication (bit-exact matches).
    
    Args:
        file_path: Path to the file.
        block_size: Size of chunks to read into memory (default 64KB).
    
    Returns:
        Hexadecimal string of the hash.
    """
    sha256 = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(block_size):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    except OSError as e:
        logger.error(f"Failed to hash {file_path}: {e}")
        raise


def calculate_prehash(file_path: Path, bytes_to_hash: int = DEFAULT_PREHASH_BYTES) -> str:
    """
    Calculate a fast pre-hash using file size and the first N bytes.

    This is intended as a cheap Tier-1 hash for triage and duplicate grouping.
    """
    sha256 = hashlib.sha256()
    try:
        size = file_path.stat().st_size
        sha256.update(str(size).encode("utf-8"))
        with file_path.open("rb") as handle:
            sha256.update(handle.read(bytes_to_hash))
        return sha256.hexdigest()
    except OSError as e:
        logger.error("Failed to prehash %s: %s", file_path, e)
        raise


def calculate_tiered_hashes(
    file_path: Path,
    prehash_bytes: int = DEFAULT_PREHASH_BYTES,
) -> dict[str, str]:
    """
    Return Tier-1 and Tier-2 hashes for a file.

    Tier-1 is a pre-hash using file size + first N bytes.
    Tier-2 is a full SHA-256 hash.
    """
    return {
        "tier1": calculate_prehash(file_path, prehash_bytes),
        "tier2": calculate_file_hash(file_path),
    }
