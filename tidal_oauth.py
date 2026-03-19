#!/usr/bin/env python3

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


CLIENT_ID = os.environ.get("TIDAL_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("TIDAL_CLIENT_SECRET", "").strip()

REDIRECT_HOST = "127.0.0.1"
REDIRECT_PORT = 8888
REDIRECT_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}{REDIRECT_PATH}"

AUTHORIZE_URL = "https://login.tidal.com/authorize"
TOKEN_URL = "https://auth.tidal.com/v1/oauth2/token"

SCOPES = [
    "search.read",
    "entitlements.read",
]

USE_PKCE = True
TIMEOUT_SECONDS = 180
TOKENS_FILE = Path("tidal_tokens.json")

auth_result: dict[str, str | None] = {
    "code": None,
    "state": None,
    "error": None,
    "error_description": None,
}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_code_verifier(length: int = 64) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return b64url(digest)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path != REDIRECT_PATH:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = parse_qs(parsed.query)

        auth_result["code"] = params.get("code", [None])[0]
        auth_result["state"] = params.get("state", [None])[0]
        auth_result["error"] = params.get("error", [None])[0]
        auth_result["error_description"] = params.get("error_description", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        if auth_result["code"]:
            self.wfile.write(
                b"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>TIDAL OAuth</title>
  </head>
  <body>
    <h1>Authorization received</h1>
    <p>You can close this window and return to the terminal.</p>
  </body>
</html>"""
            )
        else:
            self.wfile.write(
                b"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>TIDAL OAuth</title>
  </head>
  <body>
    <h1>Authorization failed</h1>
    <p>Check the terminal for details.</p>
  </body>
</html>"""
            )

    def log_message(self, format: str, *args: Any) -> None:
        return


def start_callback_server() -> HTTPServer:
    server = HTTPServer((REDIRECT_HOST, REDIRECT_PORT), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    code_challenge: str | None = None,
) -> str:
    query: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
    }

    if code_challenge:
        query["code_challenge"] = code_challenge
        query["code_challenge_method"] = "S256"

    return f"{AUTHORIZE_URL}?{urlencode(query)}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict[str, Any]:
    data: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    if client_secret:
        data["client_secret"] = client_secret

    if code_verifier:
        data["code_verifier"] = code_verifier

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def wait_for_callback(timeout_seconds: int) -> None:
    start = time.time()
    while True:
        if auth_result["code"] is not None or auth_result["error"] is not None:
            return
        if time.time() - start > timeout_seconds:
            raise TimeoutError("Timed out waiting for OAuth callback.")
        time.sleep(0.1)


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_token_payload(old_tokens: dict[str, Any], new_tokens: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old_tokens)
    merged.update(new_tokens)

    if not merged.get("refresh_token") and old_tokens.get("refresh_token"):
        merged["refresh_token"] = old_tokens["refresh_token"]

    if not merged.get("scope") and old_tokens.get("scope"):
        merged["scope"] = old_tokens["scope"]

    if not merged.get("user_id") and old_tokens.get("user_id"):
        merged["user_id"] = old_tokens["user_id"]

    return merged


def run_oauth_flow() -> dict[str, Any]:
    state = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier() if USE_PKCE else None
    code_challenge = generate_code_challenge(code_verifier) if code_verifier else None

    auth_url = build_authorization_url(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        scopes=SCOPES,
        state=state,
        code_challenge=code_challenge,
    )

    server = start_callback_server()

    print("Opening browser for TIDAL authorization...")
    print(auth_url)
    webbrowser.open(auth_url)

    try:
        print(f"Waiting for callback on {REDIRECT_URI} ...")
        wait_for_callback(TIMEOUT_SECONDS)
    finally:
        server.shutdown()
        server.server_close()

    if auth_result["error"]:
        raise RuntimeError(
            f"OAuth error: {auth_result['error']} | "
            f"description: {auth_result['error_description']}"
        )

    if auth_result["state"] != state:
        raise RuntimeError("State mismatch.")

    code = auth_result["code"]
    if not code:
        raise RuntimeError("No authorization code received.")

    return exchange_code_for_tokens(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        code=code,
        redirect_uri=REDIRECT_URI,
        code_verifier=code_verifier,
    )


def run_refresh_flow() -> dict[str, Any]:
    if not TOKENS_FILE.exists():
        raise FileNotFoundError(f"{TOKENS_FILE} does not exist.")

    old_tokens = load_json(TOKENS_FILE)
    refresh_token = old_tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh_token found in tidal_tokens.json.")

    new_tokens = refresh_access_token(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        refresh_token=refresh_token,
    )

    return merge_token_payload(old_tokens, new_tokens)


def main() -> int:
    if not CLIENT_ID:
        print("Missing TIDAL_CLIENT_ID environment variable.")
        return 1

    if not CLIENT_SECRET:
        print("Missing TIDAL_CLIENT_SECRET environment variable.")
        return 1

    mode = "login"
    if len(sys.argv) > 1:
        mode = sys.argv[1].strip().lower()

    try:
        if mode == "login":
            token_response = run_oauth_flow()
        elif mode == "refresh":
            token_response = run_refresh_flow()
        else:
            print("Usage:")
            print("  python3 tidal_oauth.py login")
            print("  python3 tidal_oauth.py refresh")
            return 1
    except Exception as exc:
        print(str(exc))
        return 1

    save_json(TOKENS_FILE, token_response)
    print(f"Tokens saved to {TOKENS_FILE.resolve()}")
    print(json.dumps(
        {
            "expires_in": token_response.get("expires_in"),
            "scope": token_response.get("scope"),
            "token_type": token_response.get("token_type"),
            "user_id": token_response.get("user_id"),
            "has_access_token": bool(token_response.get("access_token")),
            "has_refresh_token": bool(token_response.get("refresh_token")),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
