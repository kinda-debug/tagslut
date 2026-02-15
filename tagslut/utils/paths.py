import logging
import os
from pathlib import Path

def sanitize_path_part(part: str, max_length: int = 140) -> str:
    """
    Sanitize a path component (folder or filename) for macOS/Unix.
    - Removes /
    - Limits length to prevent 'File name too long' errors.
    - Default limit is conservative (MacOS limit is 255 bytes, but full path limits exist).
    """
    if not part:
        return "Unknown"

    # Replace slashes and other dangerous characters
    sanitized = part.replace("/", "_").replace(":", "-").strip()

    # Truncate if too long (preserving extension if it looks like a file)
    if len(sanitized) > max_length:
        if "." in sanitized and len(sanitized.split(".")[-1]) <= 5:
            # It's a file with extension
            name, ext = sanitized.rsplit(".", 1)
            sanitized = name[:max_length - len(ext) - 1].strip() + "." + ext
        else:
            sanitized = sanitized[:max_length].strip()

    return sanitized or "Unknown"
from typing import Iterator, Set, Union

logger = logging.getLogger("tagslut")

SKIP_BASENAMES = {".DS_Store", "Thumbs.db"}
SKIP_PREFIXES = ("._",)

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
            for dirpath, dirnames, filenames in os.walk(root_path):
                if "_yate_db" in Path(dirpath).parts:
                    continue
                dirnames[:] = [
                    d for d in dirnames
                    if d != "_yate_db" and not d.startswith(SKIP_PREFIXES)
                ]
                for f in filenames:
                    if f in SKIP_BASENAMES or f.startswith(SKIP_PREFIXES):
                        continue
                    if Path(f).suffix.lower() in valid_exts:
                        yield Path(dirpath) / f
        else:
            for item in root_path.iterdir():
                if "_yate_db" in item.parts:
                    continue
                if item.name in SKIP_BASENAMES or item.name.startswith(SKIP_PREFIXES):
                    continue
                if item.is_file() and item.suffix.lower() in valid_exts:
                    yield item
    except OSError as e:
        logger.error(f"Error traversing {root_path}: {e}")

def sanitize_path(path: Union[str, Path]) -> Path:
    """Returns a resolved, absolute Path object."""
    return Path(path).resolve()
