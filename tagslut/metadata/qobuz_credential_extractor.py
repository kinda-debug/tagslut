from __future__ import annotations

import re
from base64 import b64decode
from collections import OrderedDict
from typing import Dict
from urllib.parse import urljoin

import requests

QOBUZ_WEB_URL = "https://play.qobuz.com"
_BUNDLE_URL_REGEX = r'src="(/resources/[\d.]+-[a-z]\d+/bundle\.js)"'
_BUNDLE_URL_FALLBACK = r'src="([^"]+bundle\.js)"'
_DIRECT_REGEX = r'production:\{api:\{appId:"(?P<app_id>\d{9})",appSecret:"(?P<app_secret>\w{32})'
_APP_ID_REGEX = r'app[_I][dD]["\'`]?\s*[=:]\s*["\'`]?(\d{5,})'
_SEED_TIMEZONE_REGEX = r'[a-z]\.initialSeed\("(?P<seed>[\w=]+)",window\.utimezone\.(?P<timezone>[a-z]+)\)'

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"


def extract_qobuz_credentials() -> Dict[str, str]:
    """
    Extract app_id and app_secret from Qobuz web player bundle.js.

    Uses streamrip's approach: direct extraction first, seed/timezone fallback.
    Returns dict with keys: app_id, app_secret.
    Raises RuntimeError if extraction fails.
    """
    try:
        web_resp = requests.get(
            f"{QOBUZ_WEB_URL}/login",
            headers={"User-Agent": _UA},
            timeout=30,
        )
        web_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Qobuz login page: {e}") from e

    html = web_resp.text or ""
    m = re.search(_BUNDLE_URL_REGEX, html) or re.search(_BUNDLE_URL_FALLBACK, html)
    if not m:
        raise RuntimeError("Failed to locate Qobuz bundle.js URL")

    bundle_url = urljoin(QOBUZ_WEB_URL + "/", m.group(1))

    try:
        js_resp = requests.get(bundle_url, headers={"User-Agent": _UA}, timeout=60)
        js_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Qobuz bundle.js from {bundle_url}: {e}") from e

    js = js_resp.text or ""

    # Approach 1: direct extraction (production:{api:{appId:"...",appSecret:"..."})
    direct = re.search(_DIRECT_REGEX, js)
    if direct:
        return {
            "app_id": direct.group("app_id"),
            "app_secret": direct.group("app_secret"),
        }

    # Approach 2: separate app_id + seed/timezone (streamrip fallback)
    app_id_match = re.search(_APP_ID_REGEX, js)
    if not app_id_match:
        raise RuntimeError("Failed to extract Qobuz app_id from bundle.js")
    app_id = app_id_match.group(1)

    seed_matches = list(re.finditer(_SEED_TIMEZONE_REGEX, js))
    if not seed_matches:
        raise RuntimeError("Failed to locate Qobuz initialSeed(...) patterns in bundle.js")

    # Streamrip prioritizes the second seed/timezone pair
    secrets: OrderedDict = OrderedDict()
    for match in seed_matches:
        seed, tz = match.group("seed", "timezone")
        secrets[tz] = seed

    if len(secrets) >= 2:
        keypairs = list(secrets.items())
        secrets.move_to_end(keypairs[1][0], last=False)

    for _tz, seed in secrets.items():
        try:
            padded = seed + "=" * (-len(seed) % 4)
            decoded = b64decode(padded.encode()).decode("utf-8")
            if decoded:
                return {"app_id": app_id, "app_secret": decoded}
        except Exception:
            continue

    raise RuntimeError("Failed to decode any Qobuz app_secret candidates from bundle.js")
