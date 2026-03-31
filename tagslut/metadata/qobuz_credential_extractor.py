from __future__ import annotations

import re
from base64 import b64decode
from typing import Dict
from urllib.parse import urljoin

import requests

QOBUZ_WEB_URL = "https://play.qobuz.com"
_BUNDLE_URL_REGEX = r'src="([^"]+bundle\.js)"'
_APP_ID_REGEX = r'app[_I][dD]["\']?\s*:\s*["\']?(\d{5,})'
_SEED_TIMEZONE_REGEX = r'initialSeed\("([^"]+)",window\.utimezone\.([a-z_]+)\)'

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"


def extract_qobuz_credentials() -> Dict[str, str]:
    """
    Extract app_id and app_secret from Qobuz web player bundle.js.

    Returns dict with keys: app_id, app_secret (first valid secret found).
    Raises RuntimeError if extraction fails.
    """
    try:
        web_resp = requests.get(QOBUZ_WEB_URL, headers={"User-Agent": _UA}, timeout=30)
        web_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Qobuz web player HTML from {QOBUZ_WEB_URL}: {e}") from e

    html = web_resp.text or ""
    m = re.search(_BUNDLE_URL_REGEX, html)
    if not m:
        raise RuntimeError("Failed to locate Qobuz bundle.js URL in web player HTML")

    bundle_url = m.group(1)
    bundle_url = urljoin(QOBUZ_WEB_URL + "/", bundle_url)

    try:
        js_resp = requests.get(bundle_url, headers={"User-Agent": _UA}, timeout=30)
        js_resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch Qobuz bundle.js from {bundle_url}: {e}") from e

    js = js_resp.text or ""

    m = re.search(_APP_ID_REGEX, js)
    if not m:
        raise RuntimeError("Failed to extract Qobuz app_id from bundle.js")
    app_id = m.group(1)

    pairs = re.findall(_SEED_TIMEZONE_REGEX, js)
    if not pairs:
        raise RuntimeError("Failed to locate Qobuz initialSeed(...) patterns in bundle.js")

    for seed, _timezone in pairs:
        try:
            padded = seed + "=" * (-len(seed) % 4)
            decoded = b64decode(padded.encode()).decode("utf-8")
        except Exception:
            continue
        if decoded:
            return {"app_id": app_id, "app_secret": decoded}

    raise RuntimeError("Failed to decode any Qobuz app_secret candidates from bundle.js")
