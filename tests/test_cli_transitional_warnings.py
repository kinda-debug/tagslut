"""Tests for transitional command deprecation notices."""

from tagslut.cli.main import _format_transitional_warning


def test_transitional_warning_includes_replacement_for_known_command() -> None:
    msg = _format_transitional_warning("tagslut _mgmt")
    assert "tagslut _mgmt" in msg
    assert "transitional legacy wrapper" in msg
    assert "tagslut index" in msg


def test_transitional_warning_for_unknown_command_is_generic() -> None:
    msg = _format_transitional_warning("tagslut unknown")
    assert "tagslut unknown" in msg
    assert "docs/SCRIPT_SURFACE.md" in msg
    assert "Recommended now:" not in msg
