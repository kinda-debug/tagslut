"""SDK-backed smoke validation flows for tagslut API integration."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, cast

import requests  # type: ignore[import-untyped]

from tagslut.metadata.providers.tagslut_api_client import get_client


def _is_not_found_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "404" in text or "not found" in text


def validate_token() -> Dict[str, Any]:
    """Introspect the configured access token and require active=True."""

    client = get_client()
    try:
        result = client.auth.introspect_token()
    except Exception as exc:
        raise RuntimeError(f"Token validation failed: {exc}") from exc

    if not isinstance(result, dict):
        raise RuntimeError(f"Token validation returned unexpected payload type: {type(result)}")

    # Beatport's introspect endpoint returns user info without an "active" field
    # Presence of user_id indicates a valid, active token
    if not result.get("user_id"):
        raise RuntimeError(f"Token not active: {result}")

    return result


def lookup_isrc(isrc: str) -> Optional[Dict[str, Any]]:
    """Look up a Beatport track by ISRC through the Catalog API.
    
    Uses direct HTTP requests instead of SDK due to SDK auth issues.
    """
    
    # Get credentials from environment
    base_url = os.getenv("TAGSLUT_API_BASE_URL") or os.getenv("base_url")
    token = os.getenv("TAGSLUT_API_ACCESS_TOKEN") or os.getenv("access_token")
    
    if not base_url or not token:
        raise RuntimeError("Missing API credentials (TAGSLUT_API_BASE_URL and TAGSLUT_API_ACCESS_TOKEN)")
    
    # Direct HTTP request bypassing broken SDK
    url = f"{base_url}/v4/catalog/tracks/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    params = {"isrc": isrc}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        # 404 = not found (return None, not an error)
        if response.status_code == 404:
            return None
            
        # Other errors raise exception
        if response.status_code != 200:
            raise RuntimeError(f"API returned {response.status_code}: {response.text}")
        
        result = response.json()
        
        # Check for empty results
        if not result:
            return None
        if result.get("count") == 0:
            return None
        if not result.get("results"):
            return None
            
        return cast(Dict[str, Any], result)
        
    except requests.RequestException as exc:
        raise RuntimeError(f"ISRC lookup failed for {isrc}: {exc}") from exc


def smoke_test(test_isrc: str) -> Dict[str, Any]:
    """Run token validation plus one ISRC lookup as an integration smoke test."""

    output: Dict[str, Any] = {
        "token_valid": False,
        "token_info": None,
        "isrc_lookup_works": False,
        "isrc_result": None,
        "errors": [],
    }

    try:
        token_info = validate_token()
        output["token_valid"] = True
        output["token_info"] = token_info
    except Exception as exc:
        output["errors"].append(f"Token validation: {exc}")

    try:
        isrc_result = lookup_isrc(test_isrc)
        output["isrc_lookup_works"] = isrc_result is not None
        output["isrc_result"] = isrc_result
    except Exception as exc:
        output["errors"].append(f"ISRC lookup: {exc}")

    return output
