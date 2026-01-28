#!/usr/bin/env python3
"""
Client that calls the Spotify pathfinder endpoint using partner headers.
"""

import json
import sys

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx")
    sys.exit(1)

from dedupe.metadata.spotify_partner_tokens import get_partner_headers

PARTNER_ENDPOINT = "https://api-partner.spotify.com/pathfinder/v1/query"


def main():
    headers = get_partner_headers()
    if not headers:
        print("Error: No partner tokens found.")
        print("Run partner_token_collector.py and POST your tokens from Postman first.")
        sys.exit(1)

    body = {
        "variables": {
            "uris": [
                "spotify:track:1xYsgHPHiR3IIdpRzkfKcE",
                "spotify:track:00xBwgnA5bj9UG0GwR3IcM",
                "spotify:track:4hl0xxnnQ2QNjZYVwizQaw",
                "spotify:track:3nM8DUmkWDLpdnu0UH0a4M",
                "spotify:track:5EhlQgSiQeoB2tnbzw5X5m"
            ]
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "697706196617419cd713ed01a204a312876b51fba591b70bf961ddc0eccd5e8e"
            }
        }
    }

    print(f"POST {PARTNER_ENDPOINT}")
    print(f"Headers: {json.dumps({k: v[:20] + '...' if len(v) > 20 else v for k, v in headers.items()}, indent=2)}")
    print(f"Body: {json.dumps(body, indent=2)}")
    print("-" * 40)

    try:
        response = httpx.post(PARTNER_ENDPOINT, headers=headers, json=body, timeout=30)
        print(f"Status: {response.status_code}")
        print("-" * 40)

        try:
            data = response.json()
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(response.text)

    except httpx.RequestError as e:
        print(f"Request failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()