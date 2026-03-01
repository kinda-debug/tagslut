from click.testing import CliRunner

from tagslut.cli.main import cli


def test_scan_command_is_not_registered() -> None:
    assert "scan" not in [cmd.name for cmd in cli.commands.values()]


def test_scan_invocation_returns_no_such_command() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "--help"])
    assert result.exit_code != 0
    assert "No such command 'scan'" in result.output
