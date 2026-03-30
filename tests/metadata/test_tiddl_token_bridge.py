"""Tests for the tiddl → tokens.json bridge.

tiddl v3 stores auth in ~/.tiddl/auth.json (not config.toml).
The bridge (TokenManager._try_import_tiddl_token → sync_from_tiddl)
reads auth.json and writes live tokens into tokens.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tagslut.metadata.auth import TokenManager


def _make_tiddl_auth(tmp_path: Path, *, access_token: str = "a1",
                     refresh_token: str | None = "r1",
                     expires_at: float | None = None) -> Path:
    auth_dir = tmp_path / ".tiddl"
    auth_dir.mkdir()
    auth = {
        "token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at or (time.time() + 10_000),
        "user_id": "12345",
        "country_code": "FR",
    }
    auth_path = auth_dir / "auth.json"
    auth_path.write_text(json.dumps(auth), encoding="utf-8")
    return auth_path


def _manager_with_home(tmp_path: Path, tokens_path: Path, monkeypatch) -> TokenManager:
    """Create a TokenManager that treats tmp_path as HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return TokenManager(tokens_path=tokens_path)


def test_tiddl_bridge_no_auth_json(tmp_path: Path, monkeypatch) -> None:
    """No ~/.tiddl/auth.json → bridge skips silently, no tokens.json created."""
    tokens_path = tmp_path / "tokens.json"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_malformed_auth_json(tmp_path: Path, monkeypatch) -> None:
    """Malformed auth.json → bridge skips silently."""
    tokens_path = tmp_path / "tokens.json"
    auth_dir = tmp_path / ".tiddl"
    auth_dir.mkdir()
    (auth_dir / "auth.json").write_text("not valid json{{", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_expired_token_skipped(tmp_path: Path, monkeypatch) -> None:
    """Expired tiddl token → bridge skips, does not import stale token."""
    tokens_path = tmp_path / "tokens.json"
    _make_tiddl_auth(tmp_path, expires_at=time.time() - 3600)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    TokenManager(tokens_path=tokens_path)

    assert tokens_path.exists() is False


def test_tiddl_bridge_imports_token_when_tidal_missing(tmp_path: Path, monkeypatch) -> None:
    """Valid tiddl auth.json, no tidal in tokens.json → token imported."""
    tokens_path = tmp_path / "tokens.json"
    _make_tiddl_auth(tmp_path, access_token="live_access", refresh_token="live_refresh")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    manager = TokenManager(tokens_path=tokens_path)

    token = manager.get_token("tidal")
    assert token is not None
    assert token.access_token == "live_access"

    saved = json.loads(tokens_path.read_text(encoding="utf-8"))
    assert saved["tidal"]["access_token"] == "live_access"


def test_tiddl_bridge_imports_token_when_tidal_expired(tmp_path: Path, monkeypatch) -> None:
    """Expired tidal token in tokens.json → replaced by live tiddl token."""
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(json.dumps({
        "tidal": {"access_token": "old", "refresh_token": "old_r",
                  "expires_at": time.time() - 3600}
    }), encoding="utf-8")
    _make_tiddl_auth(tmp_path, access_token="fresh_access", refresh_token="fresh_refresh")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    manager = TokenManager(tokens_path=tokens_path)

    token = manager.get_token("tidal")
    assert token is not None
    assert token.access_token == "fresh_access"


def test_tiddl_bridge_does_not_run_when_tidal_valid(tmp_path: Path, monkeypatch) -> None:
    """Valid non-expired tidal token already in tokens.json → bridge not called."""
    tokens_path = tmp_path / "tokens.json"
    tokens_path.write_text(json.dumps({
        "tidal": {"access_token": "good", "refresh_token": "good_r",
                  "expires_at": time.time() + 7200}
    }), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    called = []
    monkeypatch.setattr(TokenManager, "_try_import_tiddl_token",
                        lambda self: called.append(True))

    TokenManager(tokens_path=tokens_path)

    assert not called, "_try_import_tiddl_token should not be called when token is valid"
