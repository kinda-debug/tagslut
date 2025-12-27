import logging
import os
import shutil
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("dedupe")

def delete_file(path: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    Safely deletes a file.
    
    Args:
        path: Path to the file.
        dry_run: If True, only logs the action.
        
    Returns:
        Tuple[bool, str]: (Success, Message)
    """
    if not path.exists():
        msg = f"File not found: {path}"
        logger.warning(msg)
        return False, msg

    if dry_run:
        logger.info(f"[DRY RUN] Would delete: {path}")
        return True, "Dry run simulated deletion"

    try:
        os.remove(path)
        logger.info(f"Deleted: {path}")
        return True, "Deleted"
    except OSError as e:
        msg = f"Failed to delete {path}: {e}"
        logger.error(msg)
        return False, msg

def move_file(src: Path, dest: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """
    Safely moves a file.
    """
    if not src.exists():
        return False, f"Source not found: {src}"
    
    if dest.exists():
        return False, f"Destination exists: {dest}"

    if dry_run:
        logger.info(f"[DRY RUN] Would move: {src} -> {dest}")
        return True, "Dry run simulated move"

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dest)
        logger.info(f"Moved: {src} -> {dest}")
        return True, "Moved"
    except OSError as e:
        msg = f"Failed to move {src}: {e}"
        logger.error(msg)
        return False, msg
