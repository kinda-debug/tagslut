"""Filter macOS system files from scans."""

from pathlib import Path
from typing import List


class MacOSFilters:
    """Filter AppleDouble and other macOS metadata files."""

    # macOS metadata patterns to filter
    MACOS_PATTERNS = {
        '._*',  # AppleDouble resource forks
        '.DS_Store',  # Directory metadata
        '.AppleDouble',  # Resource fork directory
        '.TemporaryItems',  # Temporary directory
        '.Spotlight-V100',  # Spotlight index
        '.Trashes',  # Trash directory
    }

    @staticmethod
    def is_macos_metadata(file_path: str) -> bool:
        """Check if file is macOS metadata."""
        filename = Path(file_path).name

        # Check exact matches
        if filename in MacOSFilters.MACOS_PATTERNS:
            return True

        # Check pattern matches
        if filename.startswith('._'):
            return True

        return False

    @staticmethod
    def filter_files(files: List[str]) -> List[str]:
        """Filter out macOS metadata files."""
        return [f for f in files if not MacOSFilters.is_macos_metadata(f)]

    @staticmethod
    def count_filtered(files: List[str]) -> dict:  # type: ignore  # TODO: mypy-strict
        """Count filtered files."""
        total = len(files)
        filtered = MacOSFilters.filter_files(files)
        return {
            'total': total,
            'kept': len(filtered),
            'removed': total - len(filtered),
        }
