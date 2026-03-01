"""
File Filters Module

Utilities for filtering junk files from deduplication operations.
Handles macOS metadata files, resource forks, and other common artifacts.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# macOS-specific junk patterns
MACOS_JUNK_PATTERNS = [
    r"^\._.*",  # AppleDouble resource fork prefix
    r".*/\._.*",  # Nested resource fork
    r"\.DS_Store$",  # macOS directory index
    r"\.Spotlight-V100(/|$)",  # Spotlight index
    r"\.fseventsd(/|$)",  # File system events
    r"\.Trashes(/|$)",  # Trash folders
    r"\.TemporaryItems(/|$)",  # Temporary items
    r"__MACOSX(/|$)",  # macOS archive artifacts
]

# General junk patterns
GENERAL_JUNK_PATTERNS = [
    r"Thumbs\.db$",  # Windows thumbnails
    r"desktop\.ini$",  # Windows folder settings
    r"\.directory$",  # KDE folder settings
    r"~\$.*",  # Office temp files
    r".*\.tmp$",  # Temporary files
    r".*\.bak$",  # Backup files
]

# Audio-specific junk
AUDIO_JUNK_PATTERNS = [
    r"\.cue$",  # CUE sheets (not audio)
    r"\.log$",  # Rip logs
    r"\.m3u8?$",  # Playlists
    r"\.accurip$",  # AccurateRip data
    r"\.ffp$",  # Fingerprint files
]


@dataclass
class FilterResult:
    """Result of a junk file check."""

    path: str
    is_junk: bool
    category: Optional[str] = None
    pattern: Optional[str] = None


class FileFilter:
    """
    Filter junk files from file operations.

    Categories:
    - macos: macOS-specific metadata and resource forks
    - general: Cross-platform temp/backup files
    - audio: Audio metadata files (not actual audio)
    """

    def __init__(
        self,
        include_macos: bool = True,
        include_general: bool = True,
        include_audio: bool = False,
    ):
        """
        Initialize the filter.

        Args:
            include_macos: Filter macOS junk (default: True)
            include_general: Filter general junk (default: True)
            include_audio: Filter audio metadata files (default: False)
        """
        self.patterns: Dict[str, List[re.Pattern]] = {}  # type: ignore  # TODO: mypy-strict

        if include_macos:
            self.patterns["macos"] = [re.compile(p) for p in MACOS_JUNK_PATTERNS]

        if include_general:
            self.patterns["general"] = [re.compile(p) for p in GENERAL_JUNK_PATTERNS]

        if include_audio:
            self.patterns["audio"] = [re.compile(p) for p in AUDIO_JUNK_PATTERNS]

        self.stats = {"checked": 0, "filtered": 0, "by_category": {}}

    def is_junk(self, file_path: str | Path) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if a file is junk.

        Args:
            file_path: Path to check

        Returns:
            Tuple of (is_junk, category, matching_pattern)
        """
        path_str = str(file_path)
        self.stats["checked"] += 1  # type: ignore  # TODO: mypy-strict

        for category, patterns in self.patterns.items():
            for pattern in patterns:
                if pattern.search(path_str):
                    self.stats["filtered"] += 1  # type: ignore  # TODO: mypy-strict
                    self.stats["by_category"][category] = (  # type: ignore  # TODO: mypy-strict
                        self.stats["by_category"].get(category, 0) + 1  # type: ignore  # TODO: mypy-strict
                    )
                    return True, category, pattern.pattern

        return False, None, None

    def check(self, file_path: str | Path) -> FilterResult:
        """
        Check a file and return detailed result.

        Args:
            file_path: Path to check

        Returns:
            FilterResult with details
        """
        is_junk, category, pattern = self.is_junk(file_path)
        return FilterResult(
            path=str(file_path),
            is_junk=is_junk,
            category=category,
            pattern=pattern,
        )

    def filter_paths(self, paths: List[str | Path]) -> List[str]:
        """
        Filter a list of paths, returning only non-junk.

        Args:
            paths: List of paths to filter

        Returns:
            List of non-junk paths
        """
        return [str(p) for p in paths if not self.is_junk(p)[0]]

    def get_stats(self) -> Dict:  # type: ignore  # TODO: mypy-strict
        """Get filtering statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self.stats = {"checked": 0, "filtered": 0, "by_category": {}}


# Convenience functions


def is_junk_file(path: str | Path, include_audio: bool = False) -> bool:
    """
    Quick check if a file is junk.

    Args:
        path: File path to check
        include_audio: Include audio metadata files as junk

    Returns:
        True if the file is junk
    """
    filter = FileFilter(include_audio=include_audio)
    return filter.is_junk(path)[0]


def is_macos_metadata(path: str | Path) -> bool:
    """
    Check if a file is macOS metadata.

    Args:
        path: File path to check

    Returns:
        True if the file is macOS metadata
    """
    filter = FileFilter(include_macos=True, include_general=False)
    is_junk, category, _ = filter.is_junk(path)
    return is_junk and category == "macos"


def filter_macos_metadata(paths: List[str | Path]) -> List[str]:
    """
    Filter macOS metadata files from a list.

    Args:
        paths: List of paths

    Returns:
        List with macOS metadata removed
    """
    filter = FileFilter(include_macos=True, include_general=False)
    return filter.filter_paths(paths)


# Legacy compatibility - AppleDoubleFilter class


class AppleDoubleFilter:
    """
    Filter AppleDouble files from deduplication results.

    Legacy compatibility class - prefer FileFilter for new code.
    """

    def __init__(self):  # type: ignore  # TODO: mypy-strict
        self._filter = FileFilter(include_macos=True, include_general=False)
        self.filtered_count = 0
        self.appledouble_files: List[str] = []

    def is_appledouble(self, file_path: str) -> Tuple[bool, str]:
        """Check if file is AppleDouble resource fork."""
        is_junk, _, pattern = self._filter.is_junk(file_path)
        reason = f"Matches pattern: {pattern}" if is_junk else ""
        return is_junk, reason

    def filter_recommendations(self, recommendations: List[Dict]) -> List[Dict]:  # type: ignore  # TODO: mypy-strict
        """Filter out AppleDouble files from recommendations."""
        filtered = []

        for rec in recommendations:
            file1 = rec.get("file1", "")
            file2 = rec.get("file2", "")

            is_ad1, _ = self.is_appledouble(file1)
            is_ad2, _ = self.is_appledouble(file2)

            if is_ad1 or is_ad2:
                self.filtered_count += 1
                if is_ad1:
                    self.appledouble_files.append(file1)
                if is_ad2:
                    self.appledouble_files.append(file2)
            else:
                filtered.append(rec)

        return filtered

    def get_stats(self) -> Dict:  # type: ignore  # TODO: mypy-strict
        return {
            "filtered_count": self.filtered_count,
            "appledouble_files_found": len(set(self.appledouble_files)),
        }
