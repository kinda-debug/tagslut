from __future__ import annotations

from pathlib import Path

import click
from click.testing import CliRunner

from tagslut.cli.commands.auth import register_auth_group


@click.group()
def cli() -> None:
    pass


register_auth_group(cli)


def test_auth_logout_tidal_invokes_tiddl_and_clears_tokens(monkeypatch) -> None:
    calls: dict[str, int] = {"tiddl": 0, "logout_tidal": 0}

    class _FakeTokenManager:
        def __init__(self, path=None):
            self.path = path

        def logout_tidal(self) -> None:
            calls["logout_tidal"] += 1

    def _fake_run(args, check=False):  # type: ignore[no-untyped-def]
        assert args == ["tiddl", "auth", "logout"]
        calls["tiddl"] += 1

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(path),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )
    monkeypatch.setattr("tagslut.cli.commands.auth.subprocess.run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "logout", "tidal"])

    assert result.exit_code == 0
    assert calls["tiddl"] == 1
    assert calls["logout_tidal"] == 1
    assert "TIDAL logged out" in result.output


def test_auth_tidal_logout_legacy_wrapper(monkeypatch) -> None:
    calls: dict[str, int] = {"logout_tidal": 0}

    class _FakeTokenManager:
        def __init__(self, path=None):
            self.path = path

        def logout_tidal(self) -> None:
            calls["logout_tidal"] += 1

    def _fake_run(args, check=False):  # type: ignore[no-untyped-def]
        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(
        "tagslut.metadata.auth.TokenManager",
        lambda path=None: _FakeTokenManager(path),
    )
    monkeypatch.setattr(
        "tagslut.metadata.auth.DEFAULT_TOKENS_PATH",
        Path("/tmp/tokens.json"),
    )
    monkeypatch.setattr("tagslut.cli.commands.auth.subprocess.run", _fake_run)

    runner = CliRunner()
    result = runner.invoke(cli, ["auth-tidal-logout"])

    assert result.exit_code == 0
    assert calls["logout_tidal"] == 1


def test_auth_logout_rejects_non_tidal_provider() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["auth", "logout", "beatport"])
    assert result.exit_code == 1
    assert "Unsupported provider 'beatport'" in result.output

