from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from tagslut.cli.commands.auth import register_auth_group
from tagslut.metadata.auth import TokenInfo


@click.group()
def cli() -> None:
    pass


register_auth_group(cli)


class _FakeTokenManager:
    def __init__(self, token):
        self._token = token

    def ensure_valid_token(self, provider: str):
        return self._token


def test_auth_token_get_prints_only_access_token(monkeypatch) -> None:
    token = TokenInfo(
        access_token="abc123token",
        expires_at=4102444800.0,
    )

    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(token),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "token-get", "beatport"])

    assert result.exit_code == 0
    assert result.output == "abc123token\n"


def test_top_level_token_get_prints_only_access_token(monkeypatch) -> None:
    token = TokenInfo(
        access_token="top-level-token",
        expires_at=4102444800.0,
    )

    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(token),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["token-get", "beatport"])

    assert result.exit_code == 0
    assert result.output == "top-level-token\n"


def test_auth_token_get_exits_1_when_token_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(None),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "token-get", "beatport"])

    assert result.exit_code == 1
    assert "Error: No valid Beatport token." in result.output


def test_auth_token_get_exits_1_when_token_expired(monkeypatch) -> None:
    token = TokenInfo(
        access_token="expired-token",
        expires_at=1.0,
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(token),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "token-get", "tidal"])

    assert result.exit_code == 1
    assert "Error: No valid Tidal token." in result.output


def test_auth_token_get_rejects_unknown_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "token-get", "spotify"])

    assert result.exit_code == 1
    assert "Unsupported provider 'spotify'" in result.output
