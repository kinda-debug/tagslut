from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli


def test_provider_status_command_accepts_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        "\n".join(
            [
                "[providers.tidal]",
                "metadata_enabled = false",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["provider", "status", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert "beatport" in result.output
    assert "tidal" in result.output
