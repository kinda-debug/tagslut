import subprocess
import logging
from pathlib import Path
from typing import Tuple, Literal

logger = logging.getLogger("tagslut")

IntegrityState = Literal["valid", "recoverable", "corrupt"]


def classify_flac_integrity(file_path: Path) -> Tuple[IntegrityState, str]:
    """
    Verifies the integrity of a FLAC file using the official `flac -t` command.

    Args:
        file_path: Path to the FLAC file.

    Returns:
        Tuple[IntegrityState, str]: (integrity state, raw stderr output).
    """
    if not file_path.exists():
        msg = f"File not found: {file_path}"
        logger.error(msg)
        return "corrupt", msg

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
            return "valid", ""
        
        error_msg = result.stderr.strip() or "Unknown FLAC error"
        logger.warning(f"Integrity check failed for {file_path}: {error_msg}")
        if "MD5" in error_msg.upper():
            return "recoverable", error_msg
        return "corrupt", error_msg

    except FileNotFoundError:
        logger.critical("The 'flac' executable is not found in PATH.")
        raise RuntimeError("flac binary missing")
    except Exception as e:
        logger.error(f"Unexpected error checking integrity for {file_path}: {e}")
        return "corrupt", str(e)


def check_flac_integrity(file_path: Path) -> Tuple[bool, str]:
    """Compatibility wrapper returning a boolean integrity flag."""

    state, detail = classify_flac_integrity(file_path)
    return state == "valid", detail
