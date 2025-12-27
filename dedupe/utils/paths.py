import logging
import os
from pathlib import Path
from typing import Iterator, Set, Union

logger = logging.getLogger("dedupe")

def list_files(root: Union[str, Path], extensions: Set[str], recursive: bool = True) -> Iterator[Path]:
    """
    Yields paths to files within root matching the given extensions (case-insensitive).
    """
    root_path = Path(root).resolve()
    
    if not root_path.exists():
        logger.error(f"Root path does not exist: {root_path}")
        return

    # Normalize extensions to lowercase
    valid_exts = {e.lower() for e in extensions}

    try:
        if recursive:
            for dirpath, _, filenames in os.walk(root_path):
                for f in filenames:
                    if Path(f).suffix.lower() in valid_exts:
                        yield Path(dirpath) / f
        else:
            for item in root_path.iterdir():
                if item.is_file() and item.suffix.lower() in valid_exts:
                    yield item
    except OSError as e:
        logger.error(f"Error traversing {root_path}: {e}")

def sanitize_path(path: Union[str, Path]) -> Path:
    """Returns a resolved, absolute Path object."""
    return Path(path).resolve()
