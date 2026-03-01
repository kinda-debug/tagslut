"""
Duration validation for detecting corrupted or improperly recovered audio files.

This module identifies files with suspicious durations by comparing:
1. Actual duration (from FLAC metadata)
2. Expected duration (from MusicBrainz or other metadata sources)

Common issues detected:
- R-Studio recovered files that are "stitched" together (longer than expected)
- Truncated files (shorter than expected)
- Corrupt headers reporting incorrect duration
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tagslut")

# Duration tolerance thresholds
DEFAULT_TOLERANCE_SECONDS = 2.0  # Allow 2 second variance (standard)
STRICT_TOLERANCE_SECONDS = 0.5    # Strict mode for critical validation
STITCHED_FILE_THRESHOLD = 10.0    # Flag if >10 seconds longer (likely stitched)


@dataclass
class DurationMismatch:
    """Represents a duration validation failure."""
    path: Path
    actual_duration: float
    expected_duration: float
    difference: float
    mismatch_type: str  # "too_long", "too_short", "within_tolerance"
    severity: str       # "critical", "warning", "info"
    source: str         # Where expected duration came from: "musicbrainz", "metadata", "manual"

    @property
    def is_suspicious(self) -> bool:
        """Returns True if this mismatch indicates a problem."""
        return self.severity in ("critical", "warning")

    @property
    def is_likely_stitched(self) -> bool:
        """Returns True if file is likely a stitched recovery."""
        return self.mismatch_type == "too_long" and self.difference > STITCHED_FILE_THRESHOLD


def validate_duration(
    actual_duration: float,
    expected_duration: float,
    tolerance: float = DEFAULT_TOLERANCE_SECONDS,
    source: str = "unknown",
) -> DurationMismatch:
    """
    Validates actual duration against expected duration.

    Args:
        actual_duration: Duration from FLAC file (in seconds)
        expected_duration: Duration from metadata source (in seconds)
        tolerance: Allowed variance in seconds
        source: Where expected duration came from

    Returns:
        DurationMismatch object with analysis results
    """
    difference = actual_duration - expected_duration
    abs_diff = abs(difference)

    # Determine mismatch type
    if abs_diff <= tolerance:
        mismatch_type = "within_tolerance"
        severity = "info"
    elif difference > 0:
        mismatch_type = "too_long"
        # Stitched files are critical, minor variances are warnings
        severity = "critical" if difference > STITCHED_FILE_THRESHOLD else "warning"
    else:
        mismatch_type = "too_short"
        # Truncated files are always critical
        severity = "critical"

    return DurationMismatch(
        path=Path(""),  # Will be set by caller
        actual_duration=actual_duration,
        expected_duration=expected_duration,
        difference=difference,
        mismatch_type=mismatch_type,
        severity=severity,
        source=source,
    )


def extract_expected_duration_from_tags(tags: dict) -> Optional[float]:  # type: ignore  # TODO: mypy-strict
    """
    Extracts expected duration from FLAC tags if available.

    Checks for:
    - MUSICBRAINZ_TRACK_LENGTH (milliseconds)
    - DISCOGS_DURATION (various formats)
    - Custom EXPECTED_LENGTH tags

    Args:
        tags: Dictionary of FLAC tags (lowercase keys)

    Returns:
        Expected duration in seconds, or None if not found
    """
    # MusicBrainz stores length in milliseconds
    if "musicbrainz_track_length" in tags:
        try:
            length_ms = float(tags["musicbrainz_track_length"])
            return length_ms / 1000.0
        except (ValueError, TypeError):
            pass

    # Try alternative tag names
    for key in ["expected_length", "original_length", "discogs_duration"]:
        if key in tags:
            try:
                # Assume seconds
                return float(tags[key])
            except (ValueError, TypeError):
                pass

    return None


def check_file_duration(
    actual_duration: float,
    tags: dict,  # type: ignore  # TODO: mypy-strict
    tolerance: float = DEFAULT_TOLERANCE_SECONDS,
) -> Optional[DurationMismatch]:
    """
    Checks if file duration matches expected duration from tags.

    Args:
        actual_duration: Duration from FLAC metadata
        tags: Dictionary of FLAC tags
        tolerance: Allowed variance in seconds

    Returns:
        DurationMismatch if validation fails, None if no expected duration found
    """
    expected = extract_expected_duration_from_tags(tags)
    if expected is None:
        return None

    result = validate_duration(
        actual_duration=actual_duration,
        expected_duration=expected,
        tolerance=tolerance,
        source="tags",
    )

    return result


def format_duration(seconds: float) -> str:
    """Format duration as MM:SS.ms"""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:06.3f}"


def format_mismatch_report(mismatch: DurationMismatch) -> str:
    """
    Formats a human-readable report for a duration mismatch.

    Args:
        mismatch: DurationMismatch object

    Returns:
        Formatted string for logging/reporting
    """
    actual_fmt = format_duration(mismatch.actual_duration)
    expected_fmt = format_duration(mismatch.expected_duration)
    diff_fmt = format_duration(abs(mismatch.difference))

    severity_marker = {
        "critical": "🔴 CRITICAL",
        "warning": "🟡 WARNING",
        "info": "✓ OK",
    }[mismatch.severity]

    direction = "longer" if mismatch.difference > 0 else "shorter"

    report = f"{severity_marker} Duration Mismatch\n"
    report += f"  Path: {mismatch.path}\n"
    report += f"  Actual:   {actual_fmt}\n"
    report += f"  Expected: {expected_fmt}\n"
    report += f"  Diff:     {diff_fmt} ({direction})\n"
    report += f"  Source:   {mismatch.source}\n"

    if mismatch.is_likely_stitched:
        report += "  ⚠️  LIKELY STITCHED RECOVERY FILE (R-Studio artifact)\n"

    return report
