from __future__ import annotations

from pathlib import Path

import click

from tagslut.metadata.auth import TokenManager
from tagslut.metadata.provider_registry import load_provider_activation_config
from tagslut.metadata.provider_state import (
    format_provider_status_lines,
    resolve_download_provider_statuses,
    resolve_metadata_provider_statuses,
)


def register_provider_group(cli: click.Group) -> None:
    @cli.group()
    def provider():  # type: ignore  # TODO: mypy-strict
        """Provider status and configuration helpers."""

    @provider.command("status")
    @click.option(
        "--config",
        "config_path",
        type=click.Path(path_type=Path),
        required=False,
        help="Path to providers.toml (default: ~/.config/tagslut/providers.toml)",
    )
    def provider_status(config_path: Path | None) -> None:
        activation = load_provider_activation_config(config_path)
        token_manager = TokenManager()
        metadata_statuses = resolve_metadata_provider_statuses(activation=activation, token_manager=token_manager)
        download_statuses = resolve_download_provider_statuses(activation=activation, token_manager=token_manager)
        for line in format_provider_status_lines(metadata_statuses, download_statuses):
            click.echo(line)
