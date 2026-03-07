"""Phase 4 CLI convergence surface tests."""

from __future__ import annotations

import io
import re
import sys
import types

import click
from click.testing import CliRunner

from tagslut.cli.main import (
    _TRANSITIONAL_COMMAND_REPLACEMENTS,
    cli,
)
from tagslut.cli.runtime import (
    _DEDUPE_DEPRECATION_MESSAGE,
    dedupe_entry_point,
    emit_dedupe_deprecation_warning,
)


def _parse_commands(help_text: str) -> set[str]:
    commands: set[str] = set()
    in_commands = False
    pattern = re.compile(r"^\s{2}([a-zA-Z0-9_-]+)\s{2,}")

    for line in help_text.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if not in_commands or not line.strip():
            continue
        match = pattern.match(line)
        if match:
            commands.add(match.group(1))
    return commands


def test_phase4_top_level_groups_present() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    commands = _parse_commands(result.output)

    for command in ["intake", "index", "decide", "execute", "verify", "report", "auth"]:
        assert command in commands


def test_phase4_group_subcommands_present() -> None:
    runner = CliRunner()
    required = {
        "intake": {"run", "prefilter", "process-root"},
        "index": {
            "register",
            "check",
            "duration-check",
            "duration-audit",
            "set-duration-ref",
            "enrich",
        },
        "decide": {"profiles", "plan"},
        "execute": {"move-plan", "quarantine-plan", "promote-tags"},
        "verify": {"duration", "recovery", "parity", "receipts"},
        "report": {"m3u", "duration", "recovery", "plan-summary", "dj-review"},
        "auth": {"status", "init", "refresh", "login"},
    }

    for group, expected in required.items():
        result = runner.invoke(cli, [group, "--help"])
        assert result.exit_code == 0, result.output
        commands = _parse_commands(result.output)
        assert expected.issubset(commands), f"{group} missing: {sorted(expected - commands)}"


def test_phase5_removed_top_level_commands_absent() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0, result.output
    commands = _parse_commands(result.output)

    for removed in [
        "scan",
        "recommend",
        "apply",
        "promote",
        "quarantine",
        "mgmt",
        "metadata",
        "recover",
        "m",
    ]:
        assert removed not in commands


def test_no_retired_commands_in_cli() -> None:
    retired = {
        "scan",
        "recommend",
        "apply",
        "promote",
        "quarantine",
        "mgmt",
        "metadata",
        "recover",
        "dedupe",
    }
    registered = set(cli.commands.keys())
    assert registered.isdisjoint(retired), f"Retired commands still registered: {registered & retired}"


def test_scan_not_in_cli():
    from tagslut.cli.main import cli
    assert "scan" not in cli.commands


def test_scan_not_registered_in_click_command_map() -> None:
    assert "scan" not in [cmd.name for cmd in cli.commands.values()]


def test_internal_replacement_map_targets_canonical_flows() -> None:
    assert _TRANSITIONAL_COMMAND_REPLACEMENTS["tagslut _mgmt"].startswith("tagslut index")
    assert _TRANSITIONAL_COMMAND_REPLACEMENTS["tagslut _metadata"].startswith("tagslut auth")
    assert _TRANSITIONAL_COMMAND_REPLACEMENTS["tagslut _recover"].startswith("tagslut verify")
    assert "tagslut scan" not in _TRANSITIONAL_COMMAND_REPLACEMENTS
    assert "tagslut mgmt" not in _TRANSITIONAL_COMMAND_REPLACEMENTS


def test_removed_compat_command_returns_no_such_command() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mgmt"])
    assert result.exit_code != 0
    assert "No such command 'mgmt'" in result.output


def test_report_dj_review_help_available_without_flask_import() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["report", "dj-review", "--help"])
    assert result.exit_code == 0, result.output
    assert "--db PATH" in result.output
    assert "--port INTEGER" in result.output
    assert "--open-browser / --no-open-browser" in result.output


def test_intake_process_root_help_available() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["intake", "process-root", "--help"])
    assert result.exit_code == 0, result.output
    assert "--db PATH" in result.output
    assert "--root DIRECTORY" in result.output
    assert "--providers TEXT" in result.output
    assert "--phases TEXT" in result.output
    assert "--scan-only" in result.output


def test_report_dj_review_import_error_has_install_hint(monkeypatch) -> None:
    fake_module = types.ModuleType("tagslut._web.review_app")
    monkeypatch.setitem(sys.modules, "tagslut._web.review_app", fake_module)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["report", "dj-review", "--db", "music.db", "--no-open-browser"],
    )
    assert result.exit_code != 0
    assert "Flask is required. Install with: pip install tagslut[web]" in result.output
    assert "Traceback" not in result.output


def test_report_dj_review_invokes_run_review_app(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    fake_module = types.ModuleType("tagslut._web.review_app")

    def _fake_run_review_app(**kwargs) -> None:  # type: ignore[no-untyped-def]
        calls.append(kwargs)

    fake_module.run_review_app = _fake_run_review_app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tagslut._web.review_app", fake_module)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "report",
            "dj-review",
            "--db",
            "music.db",
            "--port",
            "5051",
            "--host",
            "0.0.0.0",
            "--no-open-browser",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [
        {
            "db": "music.db",
            "port": 5051,
            "host": "0.0.0.0",
            "open_browser": False,
        }
    ]


def test_dedupe_deprecation_warning_emitted_to_stderr() -> None:
    buf = io.StringIO()
    original_stderr = sys.stderr
    sys.stderr = buf
    try:
        emit_dedupe_deprecation_warning()
    finally:
        sys.stderr = original_stderr

    output = buf.getvalue()
    assert "dedupe" in output
    assert "deprecated" in output
    assert "2026-06-01" in output
    assert "tagslut" in output


def test_dedupe_deprecation_message_contains_migration_hint() -> None:
    assert "dedupe" in _DEDUPE_DEPRECATION_MESSAGE
    assert "2026-06-01" in _DEDUPE_DEPRECATION_MESSAGE
    assert "tagslut" in _DEDUPE_DEPRECATION_MESSAGE


def test_dedupe_entry_point_emits_deprecation_message_via_click_runner(monkeypatch) -> None:
    import tagslut.cli.main as cli_main

    def fake_cli() -> None:
        click.echo("fake tagslut cli")

    @click.command()
    def invoke_dedupe() -> None:
        dedupe_entry_point()

    monkeypatch.setattr(cli_main, "cli", fake_cli)

    runner = CliRunner()
    result = runner.invoke(invoke_dedupe)

    assert result.exit_code == 0, result.output
    assert " ".join(_DEDUPE_DEPRECATION_MESSAGE.split()) in " ".join(result.output.split())
    assert "fake tagslut cli" in result.output


def test_tagslut_help_has_no_deprecation_warning() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "deprecated" not in (result.output or "")
