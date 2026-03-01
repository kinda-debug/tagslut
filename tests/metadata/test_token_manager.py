from __future__ import annotations

import time
from pathlib import Path

from tagslut.metadata.auth import TokenInfo, TokenManager


def test_token_info_is_expired_true_for_past_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 10_000.0)
    token = TokenInfo(access_token="abc", expires_at=9_000.0)

    assert token.is_expired is True


def test_token_info_is_expired_false_for_future_timestamp(monkeypatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 10_000.0)
    token = TokenInfo(access_token="abc", expires_at=11_000.0)

    assert token.is_expired is False


def test_token_info_is_expired_false_when_expiry_unknown() -> None:
    assert TokenInfo(access_token="abc", expires_at=None).is_expired is False
    assert TokenInfo(access_token="abc", expires_at=0).is_expired is False


def test_token_manager_init_template_creates_file(tmp_path: Path) -> None:
    tokens_path = tmp_path / "tokens.json"
    manager = TokenManager(tokens_path=tokens_path)

    manager.init_template()

    assert tokens_path.exists()
    content = tokens_path.read_text(encoding="utf-8")
    assert '"beatport"' in content
    assert '"tidal"' in content


def test_token_manager_init_template_no_overwrite_existing(tmp_path: Path) -> None:
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text('{"existing": true}', encoding="utf-8")
    manager = TokenManager(tokens_path=tokens_path)

    manager.init_template()

    assert tokens_path.read_text(encoding="utf-8") == '{"existing": true}'


def test_token_manager_status_contains_provider_keys(tmp_path: Path) -> None:
    manager = TokenManager(tokens_path=tmp_path / "tokens.json")
    manager.init_template()

    status = manager.status()

    assert {"beatport", "tidal", "qobuz", "itunes", "apple_music"} <= set(status)


def test_token_manager_set_and_get_token_round_trip(tmp_path: Path) -> None:
    manager = TokenManager(tokens_path=tmp_path / "tokens.json")
    manager.set_token("tidal", access_token="token-1", refresh_token="r1", expires_at=123.0)

    token = manager.get_token("tidal")

    assert token is not None
    assert token.access_token == "token-1"
    assert token.refresh_token == "r1"
    assert token.expires_at == 123.0


def test_token_manager_get_token_returns_none_for_missing_provider(tmp_path: Path) -> None:
    manager = TokenManager(tokens_path=tmp_path / "tokens.json")

    assert manager.get_token("spotify") is None
