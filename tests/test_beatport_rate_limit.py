from __future__ import annotations

from typing import Any

import httpx

from tagslut.metadata.providers.beatport import BeatportProvider


def test_beatport_no_auth_retries_on_429(monkeypatch) -> None:
    provider = BeatportProvider(token_manager=None)

    # Avoid waiting during tests
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    monkeypatch.setattr("tagslut.metadata.providers.beatport.time.sleep", lambda _: None)

    calls: list[int] = []

    def fake_request(method: str, url: str, headers: dict[str, Any], params=None, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200)

    class DummyClient:
        def request(self, method, url, headers=None, params=None, **kwargs):
            return fake_request(method, url, headers or {}, params=params, **kwargs)

    provider._client = DummyClient()  # type: ignore[assignment]

    response = provider._make_request_no_auth("GET", "https://example.com")
    assert response is not None
    assert response.status_code == 200
    assert len(calls) == 2


def test_beatport_search_by_isrc_without_auth_skips_catalog_api(monkeypatch) -> None:
    provider = BeatportProvider(token_manager=None)

    calls: list[tuple[str, str]] = []

    def fail_if_called(method: str, url: str, headers: dict[str, Any], params=None, **kwargs):
        calls.append((method, url))
        raise AssertionError("search_by_isrc should not call Beatport catalog API without auth")

    class DummyClient:
        def request(self, method, url, headers=None, params=None, **kwargs):
            return fail_if_called(method, url, headers or {}, params=params, **kwargs)

    provider._client = DummyClient()  # type: ignore[assignment]

    results = provider.search_by_isrc("GBEXH2900051")
    assert results == []
    assert calls == []
