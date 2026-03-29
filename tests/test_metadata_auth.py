from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from tagslut.metadata.auth import TokenManager, TokenInfo, BEATPORT_DJ_CLIENT_ID


class _Response:
    def __init__(self, payload: dict, should_raise: bool = False) -> None:
        self._payload = payload
        self._should_raise = should_raise
        self.request = httpx.Request("POST", "https://api.beatport.com/v4/auth/o/token/")

    def raise_for_status(self) -> None:
        if self._should_raise:
            raise httpx.HTTPStatusError(
                "error",
                request=self.request,
                response=httpx.Response(400, request=self.request),
            )

    def json(self) -> dict:
        return self._payload


def _write_tokens(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_refresh_beatport_token_uses_refresh_token_when_present(monkeypatch, tmp_path: Path) -> None:
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(
        tokens_path,
        {
            "beatport": {
                "access_token": "old-access",
                "refresh_token": "refresh-123",
                "expires_at": time.time() - 3600,
            }
        },
    )
    manager = TokenManager(tokens_path)

    seen: dict = {}

    def _fake_post(url: str, headers: dict, data: dict, timeout: float):
        seen["url"] = url
        seen["headers"] = headers
        seen["data"] = data
        seen["timeout"] = timeout
        return _Response(
            {
                "access_token": "new-access",
                "refresh_token": "refresh-456",
                "expires_in": 7200,
                "token_type": "Bearer",
            }
        )

    monkeypatch.setattr(httpx, "post", _fake_post)

    token = manager.refresh_beatport_token()

    assert token is not None
    assert token.access_token == "new-access"
    assert token.refresh_token == "refresh-456"
    assert seen["url"] == "https://api.beatport.com/v4/auth/o/token/"
    assert seen["data"]["grant_type"] == "refresh_token"
    assert seen["data"]["refresh_token"] == "refresh-123"
    assert seen["data"]["client_id"] == BEATPORT_DJ_CLIENT_ID


def test_refresh_beatport_token_falls_back_to_existing_valid_manual_token_when_refresh_fails(  # noqa: E501
    monkeypatch, tmp_path: Path
) -> None:
    tokens_path = tmp_path / "tokens.json"
    _write_tokens(
        tokens_path,
        {
            "beatport": {
                "access_token": "still-valid",
                "refresh_token": "refresh-123",
                "expires_at": time.time() + 7200,
            }
        },
    )
    manager = TokenManager(tokens_path)

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _Response({}, should_raise=True))

    token = manager.refresh_beatport_token()

    assert token is not None
    assert isinstance(token, TokenInfo)
    assert token.access_token == "still-valid"
