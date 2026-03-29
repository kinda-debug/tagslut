from __future__ import annotations

import json
import time
from pathlib import Path

from tagslut.metadata.auth import TokenManager


def test_tiddl_bridge_no_config_file(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    monkeypatch.setenv("TIDDL_CONFIG", str(tmp_path / "missing.toml"))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_malformed_toml(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    config_path = tmp_path / "config.toml"
    config_path.write_text("not = [valid", encoding="utf-8")
    monkeypatch.setenv("TIDDL_CONFIG", str(config_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_missing_token_section(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    config_path = tmp_path / "config.toml"
    config_path.write_text('[other]\nrefresh_token = "r1"\n', encoding="utf-8")
    monkeypatch.setenv("TIDDL_CONFIG", str(config_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_empty_refresh_token(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    config_path = tmp_path / "config.toml"
    config_path.write_text('[token]\nrefresh_token = ""\n', encoding="utf-8")
    monkeypatch.setenv("TIDDL_CONFIG", str(config_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_imports_token_when_missing_in_tokens_json(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                "[token]",
                'access_token = "a1"',
                'refresh_token = "r1"',
                f"expires_at = {int(time.time()) + 10_000}",
                'token_type = "Bearer"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIDDL_CONFIG", str(config_path))

    manager = TokenManager(tokens_path=tokens_path)

    token = manager.get_token("tidal")
    assert token is not None
    assert token.refresh_token == "r1"

    saved = json.loads(tokens_path.read_text(encoding="utf-8"))
    assert saved["tidal"]["refresh_token"] == "r1"


def test_tiddl_bridge_does_not_run_when_tokens_json_has_refresh_token(
    tmp_path: Path, monkeypatch
) -> None:
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(
        json.dumps({"tidal": {"access_token": "a1", "refresh_token": "r1"}}, indent=2),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIDDL_CONFIG", str(tmp_path / "should-not-be-read.toml"))
    monkeypatch.setattr(
        TokenManager,
        "_try_import_tiddl_token",
        lambda self: (_ for _ in ()).throw(AssertionError("_try_import_tiddl_token called")),
    )

    manager = TokenManager(tokens_path=tokens_path)

    assert (manager._tokens.get("tidal") or {}).get("refresh_token") == "r1"


def test_tiddl_bridge_respects_tiddl_config_env_var(tmp_path: Path, monkeypatch) -> None:
    tokens_path = tmp_path / "tokens.json"
    custom_config_path = tmp_path / "custom.toml"
    custom_config_path.write_text(
        "\n".join(["[token]", 'access_token = "a2"', 'refresh_token = "r2"', ""]),
        encoding="utf-8",
    )
    monkeypatch.setenv("TIDDL_CONFIG", str(custom_config_path))

    manager = TokenManager(tokens_path=tokens_path)

    token = manager.get_token("tidal")
    assert token is not None
    assert token.refresh_token == "r2"
