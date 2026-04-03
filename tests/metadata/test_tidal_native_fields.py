from __future__ import annotations

import httpx

from tagslut.metadata.providers.tidal import TidalProvider


def test_tidal_normalize_populates_native_fields(monkeypatch) -> None:
    provider = TidalProvider(token_manager=None)

    def boom(*args, **kwargs):
        raise AssertionError("v1 fallback should not be called for complete v2 payload")

    monkeypatch.setattr(TidalProvider, "_make_request", boom)

    resource = {
        "id": "123",
        "type": "tracks",
        "attributes": {
            "title": "Test Track",
            "duration": "PT3M45S",
            "bpm": 128,
            "key": "FSharp",
            "keyScale": "MINOR",
            "djReady": True,
            "stemReady": False,
            "replayGain": {"track": {"value": -8.0}, "album": -7.5},
        },
        "relationships": {},
    }

    track = provider._normalize_track(resource, included_index={})
    assert track is not None
    assert track.tidal_bpm == 128.0
    assert track.tidal_key == "FSharp"
    assert track.tidal_key_scale == "MINOR"
    assert track.tidal_camelot == "11A"
    assert track.tidal_dj_ready == 1
    assert track.tidal_stem_ready == 0
    assert track.replay_gain_track == -8.0
    assert track.replay_gain_album == -7.5


def test_tidal_normalize_missing_fields_keeps_none(monkeypatch) -> None:
    provider = TidalProvider(token_manager=None)

    def fake_make_request(self, method, url, headers=None, params=None, **kwargs):
        return httpx.Response(200, json={})

    monkeypatch.setattr(TidalProvider, "_make_request", fake_make_request)
    monkeypatch.setattr("tagslut.metadata.providers.tidal.time.sleep", lambda *_args, **_kwargs: None)

    resource = {
        "id": "123",
        "type": "tracks",
        "attributes": {"title": "Test Track", "duration": "PT3M45S"},
        "relationships": {},
    }

    track = provider._normalize_track(resource, included_index={})
    assert track is not None
    assert track.tidal_bpm is None
    assert track.tidal_key is None
    assert track.tidal_key_scale is None
    assert track.tidal_camelot is None
    assert track.tidal_dj_ready is None
    assert track.tidal_stem_ready is None
    assert track.replay_gain_track is None
    assert track.replay_gain_album is None

