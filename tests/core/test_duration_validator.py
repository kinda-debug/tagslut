from __future__ import annotations

import pytest

from tagslut.core.duration_validator import (
    DurationMismatch,
    check_file_duration,
    validate_duration,
)


def _tags_with_expected_seconds(seconds: float) -> dict[str, str]:
    return {"expected_length": str(seconds)}


def test_check_file_duration_within_tolerance_returns_info() -> None:
    mismatch = check_file_duration(300.9, _tags_with_expected_seconds(300.0), tolerance=1.0)
    assert isinstance(mismatch, DurationMismatch)
    assert mismatch.mismatch_type == "within_tolerance"
    assert mismatch.severity == "info"


def test_check_file_duration_truncated_file_is_critical_too_short() -> None:
    mismatch = check_file_duration(280.0, _tags_with_expected_seconds(300.0), tolerance=1.0)
    assert mismatch is not None
    assert mismatch.mismatch_type == "too_short"
    assert mismatch.severity == "critical"


def test_check_file_duration_extended_file_warning_and_critical_threshold() -> None:
    warning = check_file_duration(306.0, _tags_with_expected_seconds(300.0), tolerance=1.0)
    critical = check_file_duration(311.0, _tags_with_expected_seconds(300.0), tolerance=1.0)

    assert warning is not None and warning.mismatch_type == "too_long" and warning.severity == "warning"
    assert critical is not None and critical.mismatch_type == "too_long" and critical.severity == "critical"


def test_zero_length_duration_handling() -> None:
    mismatch = check_file_duration(0.0, _tags_with_expected_seconds(300.0), tolerance=1.0)
    assert mismatch is not None
    assert mismatch.mismatch_type == "too_short"
    assert mismatch.severity == "critical"


def test_none_duration_handling_raises_type_error() -> None:
    with pytest.raises(TypeError):
        check_file_duration(None, _tags_with_expected_seconds(300.0), tolerance=1.0)  # type: ignore[arg-type]


def test_tolerance_boundary_values_are_within_tolerance() -> None:
    at_upper = validate_duration(actual_duration=302.0, expected_duration=300.0, tolerance=2.0)
    at_lower = validate_duration(actual_duration=298.0, expected_duration=300.0, tolerance=2.0)

    assert at_upper.mismatch_type == "within_tolerance"
    assert at_lower.mismatch_type == "within_tolerance"


def test_status_string_outputs_match_expected_values() -> None:
    ok = validate_duration(actual_duration=300.0, expected_duration=300.0, tolerance=1.0)
    short = validate_duration(actual_duration=299.0, expected_duration=300.0, tolerance=0.5)
    long = validate_duration(actual_duration=301.0, expected_duration=300.0, tolerance=0.5)

    assert ok.mismatch_type == "within_tolerance"
    assert short.mismatch_type == "too_short"
    assert long.mismatch_type == "too_long"
