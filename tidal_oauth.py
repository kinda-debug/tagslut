#!/usr/bin/env python3
"""TIDAL OAuth 2.0 helper — PKCE login + refresh.

Usage:
    python3 tidal_oauth.py [login|refresh]

Environment variables required:
    TIDAL_CLIENT_ID      — your TIDAL app client ID
    TIDAL_CLIENT_SECRET  — your TIDAL app client secret

Tokens are saved to tidal_tokens.json in the current directory.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

# ── Configuration ─────────────────────────────────────────────────────────────

CLIENT_ID     = os.environ.get("TIDAL_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("TIDAL_CLIENT_SECRET", "").strip()

REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8888
REDIRECT_PATH = "/callback"
REDIRECT_URI  = f"http://{REDIRECT_HOST}:{REDIRECT_PORT}{REDIRECT_PATH}"

AUTHORIZE_URL = "https://login.tidal.com/authorize"
TOKEN_URL     = "https://auth.tidal.com/v1/oauth2/token"

SCOPES          = ["search.read", "entitlements.read"]
TIMEOUT_SECONDS = 180
TOKENS_FILE     = Path("tidal_tokens.json")

# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_code_verifier(length: int = 64) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _generate_code_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())

# ── Callback server ───────────────────────────────────────────────────────────

_HTML_OK = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>TIDAL OAuth</title></head>
<body><h1>Authorization received</h1>
<p>You can close this window and return to the terminal.</p>
</body></html>"""

_HTML_ERR = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>TIDAL OAuth</title></head>
<body><h1>Authorization failed</h1>
<p>Check the terminal for details.</p>
</body></html>"""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth redirect."""

    # Shared slot — written once by the first valid callback, then read by main.
    result: dict[str, str | None] = {
        "code": None,
        "state": None,
        "error": None,
        "error_description": None,
    }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != REDIRECT_PATH:
            self._respond(404, b"text/plain", b"Not found")
            return

        params = parse_qs(parsed.query)
        for key in ("code", "state", "error", "error_description"):
            _CallbackHandler.result[key] = params.get(key, [None])[0]

        body = _HTML_OK if _CallbackHandler.result["code"] else _HTML_ERR
        self._respond(200, b"text/html; charset=utf-8", body)

    def _respond(self, status: int, content_type: bytes, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type.decode())
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return  # silence access log


def _start_callback_server() -> HTTPServer:
    server = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), _CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _wait_for_callback(timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        r = _CallbackHandler.result
        if r["code"] is not None or r["error"] is not None:
            return
        if time.monotonic() > deadline:
            raise TimeoutError("Timed out waiting for OAuth callback.")
        time.sleep(0.1)

# ── Token exchange ────────────────────────────────────────────────────────────

def _post_token(data: dict[str, str]) -> dict[str, Any]:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _exchange_code(
    code: str,
    redirect_uri: str,
    code_verifier: str | None,
) -> dict[str, Any]:
    data: dict[str, str] = {
        "grant_type":   "authorization_code",
        "client_id":    CLIENT_ID,
        "code":         code,
        "redirect_uri": redirect_uri,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    return _post_token(data)


def _refresh_token(refresh_token: str) -> dict[str, Any]:
    return _post_token({
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    })

# ── Token file helpers ────────────────────────────────────────────────────────

def _load_tokens() -> dict[str, Any]:
    if not TOKENS_FILE.exists():
        raise FileNotFoundError(f"{TOKENS_FILE} does not exist. Run 'login' first.")
    return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))


def _save_tokens(payload: dict[str, Any]) -> None:
    TOKENS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge new token response into old, preserving fields the server omits."""
    merged = {**old, **new}
    for key in ("refresh_token", "scope", "user_id"):
        if not merged.get(key) and old.get(key):
            merged[key] = old[key]
    return merged

# ── Flows ─────────────────────────────────────────────────────────────────────

def run_login() -> dict[str, Any]:
    """Full PKCE authorization-code flow."""
    state         = secrets.token_urlsafe(32)
    code_verifier = _generate_code_verifier()
    code_challenge = _generate_code_challenge(code_verifier)

    params: dict[str, str] = {
        "response_type":         "code",
        "client_id":             CLIENT_ID,
        "redirect_uri":          REDIRECT_URI,
        "scope":                 " ".join(SCOPES),
        "state":                 state,
        "code_challenge":        code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

    server = _start_callback_server()
    print("Opening browser for TIDAL authorization...")
    print(auth_url)
    webbrowser.open(auth_url)

    try:
        print(f"Waiting for callback on {REDIRECT_URI} ...")
        _wait_for_callback(TIMEOUT_SECONDS)
    finally:
        server.shutdown()
        server.server_close()

    result = _CallbackHandler.result

    if result["error"]:
        raise RuntimeError(
            f"OAuth error: {result['error']} | description: {result['error_description']}"
        )
    if result["state"] != state:
        raise RuntimeError("State mismatch — possible CSRF attempt.")
    if not result["code"]:
        raise RuntimeError("No authorization code received.")

    return _exchange_code(result["code"], REDIRECT_URI, code_verifier)


def run_refresh() -> dict[str, Any]:
    """Refresh using the stored refresh_token."""
    old = _load_tokens()
    rt  = old.get("refresh_token")
    if not rt:
        raise RuntimeError("No refresh_token in tidal_tokens.json. Run 'login' first.")
    return _merge(old, _refresh_token(rt))

# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    if not CLIENT_ID:
        print("Missing TIDAL_CLIENT_ID environment variable.", file=sys.stderr)
        return 1
    if not CLIENT_SECRET:
        print("Missing TIDAL_CLIENT_SECRET environment variable.", file=sys.stderr)
        return 1

    mode = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "login"

    try:
        if mode == "login":
            tokens = run_login()
        elif mode == "refresh":
            tokens = run_refresh()
        else:
            print("Usage:", file=sys.stderr)
            print("  python3 tidal_oauth.py login", file=sys.stderr)
            print("  python3 tidal_oauth.py refresh", file=sys.stderr)
            return 1
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    _save_tokens(tokens)
    print(f"Tokens saved to {TOKENS_FILE.resolve()}")
    print(json.dumps(
        {
            "expires_in":       tokens.get("expires_in"),
            "scope":            tokens.get("scope"),
            "token_type":       tokens.get("token_type"),
            "user_id":          tokens.get("user_id"),
            "has_access_token": bool(tokens.get("access_token")),
            "has_refresh_token": bool(tokens.get("refresh_token")),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())