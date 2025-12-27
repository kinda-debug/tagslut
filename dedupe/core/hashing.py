import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("dedupe")

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
