from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tagslut.metadata.auth import TokenInfo
from tagslut.metadata.models.types import MatchConfidence
from tagslut.metadata.providers.beatport import (
    BeatportAuthError,
    BeatportMalformedResponseError,
    BeatportProvider,
)


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "beatport"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _json_response(
    status_code: int,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(status_code, json=payload, headers=headers)


class _StubClient:
    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        call = {
            "method": method,
            "url": url,
            "headers": headers or {},
            "params": params or {},
            "kwargs": kwargs,
        }
        self.calls.append(call)

        key = (method, url)
        if key not in self.routes:
            raise AssertionError(f"Unexpected Beatport request: {method} {url}")

        route = self.routes[key]
        if isinstance(route, list):
            if not route:
                raise AssertionError(f"Exhausted Beatport route responses for: {method} {url}")
            route = route.pop(0)

        if callable(route):
            return route(call)
        return route


class _StubTokenManager:
    def __init__(self, token: TokenInfo | None) -> None:
        self._token = token
        self._tokens: dict[str, dict[str, Any]] = {}

    def ensure_valid_token(self, provider: str) -> TokenInfo | None:
        assert provider == "beatport"
        return self._token

    def get_credentials(self, provider: str) -> dict[str, str]:
        assert provider == "beatport"
        return {}


def _make_provider(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[tuple[str, str], Any],
) -> tuple[BeatportProvider, _StubClient]:
    monkeypatch.setenv("BEATPORT_ACCESS_TOKEN", "search-token")
    monkeypatch.setenv("BEATPORT_BASIC_AUTH_USERNAME", "catalog-user")
    monkeypatch.setenv("BEATPORT_BASIC_AUTH_PASSWORD", "catalog-pass")

    provider = BeatportProvider(token_manager=None)
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    monkeypatch.setattr("tagslut.metadata.providers.beatport.time.sleep", lambda _: None)

    stub = _StubClient(routes)
    provider._client = stub  # type: ignore[assignment]
    return provider, stub


def test_auth_config_prefers_token_manager_over_env(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("BEATPORT_ACCESS_TOKEN", "env-token")
    provider = BeatportProvider(
        token_manager=_StubTokenManager(
            TokenInfo(access_token="manager-token", expires_at=4102444800.0)
        )
    )

    with caplog.at_level("WARNING"):
        auth = provider._api_client._auth_config()  # noqa: SLF001

    assert auth.search_bearer_token == "manager-token"
    assert "environment variable as fallback" not in caplog.text


def test_auth_config_warns_when_env_fallback_used(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv("BEATPORT_ACCESS_TOKEN", "env-token")
    provider = BeatportProvider(token_manager=_StubTokenManager(None))

    with caplog.at_level("WARNING"):
        auth = provider._api_client._auth_config()  # noqa: SLF001

    assert auth.search_bearer_token == "env-token"
    assert "BEATPORT_ACCESS_TOKEN from environment variable as fallback" in caplog.text


def test_search_track_by_isrc_returns_hydrated_tracks(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, stub = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/v4/catalog/tracks/"): _json_response(
                200,
                _fixture("catalog_track_list.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/tracks/12345/"): _json_response(
                200,
                _fixture("catalog_track_detail.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/releases/999/"): _json_response(
                200,
                _fixture("catalog_release_detail.fixture"),
            ),
        },
    )

    tracks = provider.search_track_by_isrc("GBEXH2400001")

    assert len(tracks) == 1
    track = tracks[0]
    assert track.service_track_id == "12345"
    assert track.title == "Warehouse Cut"
    assert track.artist == "Artist A"
    assert track.album == "Warehouse EP"
    assert track.album_id == "999"
    assert track.catalog_number == "TOOL001"
    assert track.track_number == 4
    assert track.preview_url == "https://audio.example.com/sample/12345.mp3"
    assert track.match_confidence == MatchConfidence.EXACT
    assert track.raw["_catalog"]["id"] == 12345
    assert track.raw["_release"]["upc"] == "123456789012"
    assert stub.calls[0]["params"]["isrc"] == "GBEXH2400001"
    assert stub.calls[0]["kwargs"]["auth"] == ("catalog-user", "catalog-pass")


def test_search_track_by_isrc_returns_empty_on_no_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/v4/catalog/tracks/"): _json_response(
                200,
                {"count": 0, "next": None, "previous": None, "results": []},
            ),
        },
    )

    assert provider.search_track_by_isrc("NOHIT0000000") == []


def test_search_track_by_text_returns_single_hydrated_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, stub = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/search/v1/tracks"): _json_response(
                200,
                _fixture("search_tracks_single.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/tracks/12345/"): _json_response(
                200,
                _fixture("catalog_track_detail.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/releases/999/"): _json_response(
                200,
                _fixture("catalog_release_detail.fixture"),
            ),
        },
    )

    tracks = provider.search_track_by_text("Warehouse Cut", artist="Artist A")

    assert len(tracks) == 1
    track = tracks[0]
    assert track.service_track_id == "12345"
    assert track.title == "Warehouse Cut"
    assert track.artist == "Artist A"
    assert track.match_confidence == MatchConfidence.STRONG
    assert track.raw["_search"]["track_id"] == 12345
    assert track.raw["_catalog"]["id"] == 12345
    assert stub.calls[0]["headers"]["Authorization"] == "Bearer search-token"
    assert stub.calls[0]["params"]["q"] == "Artist A Warehouse Cut"


def test_search_track_by_text_returns_ranked_ambiguous_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    second_track = copy.deepcopy(_fixture("catalog_track_detail.fixture"))
    second_track["id"] = 54321
    second_track["name"] = "Warehouse Cut"
    second_track["release"] = "1999"
    second_track["catalog_number"] = "ALT001"
    second_track["publish_date"] = "2025-02-03"
    second_track["new_release_date"] = "2025-02-03"
    second_track["artists"] = [
        {
            "id": 200,
            "name": "Different Artist",
            "slug": "different-artist",
            "url": "https://www.beatport.com/artist/different-artist/200",
        }
    ]

    second_release = copy.deepcopy(_fixture("catalog_release_detail.fixture"))
    second_release["id"] = 1999
    second_release["name"] = "Warehouse Cut"
    second_release["catalog_number"] = "ALT001"
    second_release["publish_date"] = "2025-02-03"
    second_release["new_release_date"] = "2025-02-03"
    second_release["label"] = {"id": 88, "name": "Alternate Label", "slug": "alternate-label"}
    second_release["upc"] = "999999999999"

    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/search/v1/tracks"): _json_response(
                200,
                _fixture("search_tracks_ambiguous.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/tracks/12345/"): _json_response(
                200,
                _fixture("catalog_track_detail.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/releases/999/"): _json_response(
                200,
                _fixture("catalog_release_detail.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/tracks/54321/"): _json_response(200, second_track),
            ("GET", "https://api.beatport.com/v4/catalog/releases/1999/"): _json_response(200, second_release),
        },
    )

    tracks = provider.search_track_by_text("Warehouse Cut", artist="Artist A")

    assert [track.service_track_id for track in tracks] == ["12345", "54321"]
    assert tracks[0].artist == "Artist A"
    assert tracks[0].match_confidence == MatchConfidence.STRONG
    assert tracks[1].artist == "Different Artist"
    assert tracks[1].match_confidence == MatchConfidence.WEAK


def test_search_track_by_text_falls_back_to_web_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEATPORT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BEATPORT_BASIC_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("BEATPORT_BASIC_AUTH_PASSWORD", raising=False)

    provider = BeatportProvider(token_manager=None)
    monkeypatch.setattr(provider.rate_limiter, "wait", lambda: None)
    monkeypatch.setattr(
        provider,
        "_search_web",
        lambda query, limit=10: [_fixture("catalog_track_list.fixture")["results"][0]],
    )

    tracks = provider.search_track_by_text("Warehouse Cut", artist="Artist A")

    assert len(tracks) == 1
    assert tracks[0].service_track_id == "12345"
    assert tracks[0].match_confidence == MatchConfidence.STRONG
    assert "_search" not in tracks[0].raw


def test_fetch_by_id_falls_back_to_nextjs_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEATPORT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("BEATPORT_BASIC_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("BEATPORT_BASIC_AUTH_PASSWORD", raising=False)

    provider = BeatportProvider(token_manager=None)
    monkeypatch.setattr(
        provider,
        "_fetch_nextjs_track",
        lambda track_id, slug="track": _fixture("catalog_track_detail.fixture"),
    )

    track = provider.fetch_by_id("12345")

    assert track is not None
    assert track.service_track_id == "12345"
    assert track.match_confidence == MatchConfidence.EXACT


def test_get_track_by_id_hydrates_release(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/v4/catalog/tracks/12345/"): _json_response(
                200,
                _fixture("catalog_track_detail.fixture"),
            ),
            ("GET", "https://api.beatport.com/v4/catalog/releases/999/"): _json_response(
                200,
                _fixture("catalog_release_detail.fixture"),
            ),
        },
    )

    track = provider.get_track_by_id(12345)

    assert track.service_track_id == "12345"
    assert track.album == "Warehouse EP"
    assert track.release_date == "2025-02-01"
    assert track.match_confidence == MatchConfidence.EXACT


def test_get_track_by_id_raises_on_malformed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/v4/catalog/tracks/12345/"): _json_response(
                200,
                {"name": "Missing id"},
            ),
        },
    )

    with pytest.raises(BeatportMalformedResponseError):
        provider.get_track_by_id(12345)


def test_search_tracks_raises_auth_error_on_401(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _ = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/search/v1/tracks"): _json_response(401, {"detail": "unauthorized"}),
        },
    )

    with pytest.raises(BeatportAuthError):
        provider._api_client.search_tracks({"q": "Warehouse Cut"})  # noqa: SLF001


def test_search_tracks_retries_once_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, stub = _make_provider(
        monkeypatch,
        {
            ("GET", "https://api.beatport.com/search/v1/tracks"): [
                _json_response(429, {"detail": "slow down"}, headers={"Retry-After": "0"}),
                _json_response(200, _fixture("search_tracks_single.fixture")),
            ],
        },
    )

    payload = provider._api_client.search_tracks({"q": "Warehouse Cut"})  # noqa: SLF001

    assert payload["data"][0]["track_id"] == 12345
    assert len(stub.calls) == 2
