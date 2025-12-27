import subprocess
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("dedupe")

def check_flac_integrity(file_path: Path) -> Tuple[bool, str]:
    """
    Verifies the integrity of a FLAC file using the official `flac -t` command.

    Args:
        file_path: Path to the FLAC file.

    Returns:
        Tuple[bool, str]: (True if OK, raw stderr output for logging).
    """
    if not file_path.exists():
        msg = f"File not found: {file_path}"
        logger.error(msg)
        return False, msg

    try:
        # Run flac -t (test) silently
        # We capture stderr because that's where flac prints errors
        result = subprocess.run(
            ["flac", "-t", "--silent", str(file_path)],
            capture_output=True,
            text=True,
            check=False 
        )

        if result.returncode == 0:
            return True, ""
        
        error_msg = result.stderr.strip() or "Unknown FLAC error"
        logger.warning(f"Integrity check failed for {file_path}: {error_msg}")
        return False, error_msg

    except FileNotFoundError:
        logger.critical("The 'flac' executable is not found in PATH.")
        raise RuntimeError("flac binary missing")
    except Exception as e:
        logger.error(f"Unexpected error checking integrity for {file_path}: {e}")
        return False, str(e)
