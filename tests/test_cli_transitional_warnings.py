"""Tests for transitional command deprecation notices."""

from dedupe.cli.main import _format_transitional_warning


def test_transitional_warning_includes_replacement_for_known_command() -> None:
    msg = _format_transitional_warning("dedupe mgmt")
    assert "dedupe mgmt" in msg
    assert "transitional legacy wrapper" in msg
    assert "dedupe index" in msg


def test_transitional_warning_for_unknown_command_is_generic() -> None:
    msg = _format_transitional_warning("dedupe unknown")
    assert "dedupe unknown" in msg
    assert "docs/SCRIPT_SURFACE.md" in msg
    assert "Recommended now:" not in msg
