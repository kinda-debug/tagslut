"""Tests for legacy dedupe -> tagslut alias deprecation notices."""

from __future__ import annotations

from click.testing import CliRunner

from tagslut.cli.main import _format_dedupe_alias_warning, cli


def test_format_dedupe_alias_warning_for_dedupe() -> None:
    msg = _format_dedupe_alias_warning("dedupe")
    assert msg is not None
    assert "legacy alias" in msg
    assert "July 31, 2026" in msg
    assert "tagslut" in msg


def test_format_dedupe_alias_warning_not_emitted_for_tagslut() -> None:
    assert _format_dedupe_alias_warning("tagslut") is None
    assert _format_dedupe_alias_warning("taglslut") is None


def test_dedupe_invocation_emits_alias_warning() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], prog_name="dedupe")
    assert result.exit_code == 0
    emitted = "\n".join(part for part in (result.stderr, result.output) if part)
    assert "ALIAS DEPRECATION" in emitted
    assert "Use 'tagslut'" in emitted


def test_tagslut_invocation_does_not_emit_alias_warning() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"], prog_name="tagslut")
    assert result.exit_code == 0
    assert "ALIAS DEPRECATION" not in result.output
